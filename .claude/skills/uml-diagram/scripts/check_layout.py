#!/usr/bin/env python3
"""量測一張圖的版面品質：長寬比、交叉線、方向語意、線壓到方框。

    python3 check_layout.py diagram.drawio [more.drawio ...]
    python3 check_layout.py diagram.puml          # 需要 plantuml 或 java + plantuml.jar

.drawio 直接解析座標，不需要任何渲染器；.puml 會先渲染成 PNG 再讀尺寸，
沒有渲染環境時只回報「無法量測」，不要假裝量過（見 SKILL.md 收斂流程）。

判定門檻（與 SKILL.md 一致）：
    長寬比 0.75–1.35  ── 超出代表圖太扁或太細長，讀者要滑螢幕才拼得出全貌
    交叉線 0          ── 能靠重排消掉的交叉都算缺陷
    回頭線             ── 允許，但每一條都該是刻意的迴圈（重試、回上一步）

離開碼 0 = 全部通過，1 = 有項目未通過。
"""
import math
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ASPECT_MIN = 0.75
ASPECT_MAX = 1.35

# 每種圖型的元素上限（SKILL.md「動筆前先確定四件事」第 4 點）
ELEMENT_CAPS = {
    'class': 15,
    'sequence': 7,
    'state': 12,
    'flow': 22,      # 活動圖／流程圖：比類別圖寬鬆，但超過就該拆
    'er': 12,
    'architecture': 20,
}


# --------------------------------------------------------------------------
# .drawio 解析
# --------------------------------------------------------------------------

def _attr_float(el, name, default=0.0):
    try:
        return float(el.get(name, default))
    except (TypeError, ValueError):
        return default


def parse_drawio(path):
    """回傳 (nodes, edges)。node: id/x/y/w/h/type/label；edge: src/dst/label/waypoints。

    注意：mxCell 的 value 屬性裡的換行在 XML 屬性正規化時會變成空白，
    所以標籤只拿來計數與辨識型別，不要用它判斷行數。
    """
    root = ET.parse(path).getroot()
    nodes, edges = {}, []
    for cell in root.iter('mxCell'):
        cid = cell.get('id')
        if cid in (None, '0', '1'):
            continue
        style = cell.get('style') or ''
        if cell.get('vertex') == '1':
            geom = cell.find('mxGeometry')
            if geom is None:
                continue
            nodes[cid] = dict(
                id=cid,
                label=cell.get('value') or '',
                x=_attr_float(geom, 'x'), y=_attr_float(geom, 'y'),
                w=_attr_float(geom, 'width', 120), h=_attr_float(geom, 'height', 60),
                type=_node_type(style),
                style=style,
                parent=cell.get('parent') or '1',
            )
        elif cell.get('edge') == '1':
            pts = []
            geom = cell.find('mxGeometry')
            if geom is not None:
                arr = geom.find("Array[@as='points']")
                if arr is not None:
                    pts = [(_attr_float(p, 'x'), _attr_float(p, 'y')) for p in arr.iter('mxPoint')]
            edges.append(dict(id=cid, src=cell.get('source'), dst=cell.get('target'),
                              label=cell.get('value') or '', waypoints=pts, style=style))
    edges = [e for e in edges if e['src'] in nodes and e['dst'] in nodes]

    # mxGraph 的子節點座標是相對於父節點的（例如資料表的欄位列相對於表格本身）。
    # 這裡全部換算成絕對座標，後面所有幾何判斷才有共同的座標系。
    for nid, n in nodes.items():
        parent, guard = n['parent'], 0
        while parent in nodes and guard < 10:
            n['x'] += nodes[parent]['x']
            n['y'] += nodes[parent]['y']
            parent = nodes[parent]['parent']
            guard += 1
    return nodes, edges


def kin_of(nid, nodes):
    """一個節點的「自己人」：自己、父節點、以及同一個父節點底下的兄弟。
    欄位列的線從列的左右緣出發就已經離開整張表了，把表本身算成障礙物是假警報。"""
    out = {nid}
    parent = nodes[nid].get('parent', '1')
    if parent != '1' and parent in nodes:
        out.add(parent)
        out.update(k for k, v in nodes.items() if v.get('parent') == parent)
    out.update(k for k, v in nodes.items() if v.get('parent') == nid)
    return out


def _on_a_side(a):
    """錨點是否貼在某一條邊上：一個座標剛好是 0 或 1，另一個落在邊上。

    預設用該邊的中點（矩形是邊界中點、菱形是頂點）。但同一個節點同一側接了多條線時，
    要沿那條邊把錨點分開——共用一個錨點的話，那幾條線在分岔前完全重合，
    看起來只有一條。所以這裡驗的是「有沒有貼在邊上」，不是「是不是正中央」。
    """
    x, y = a
    return ((x in (0.0, 1.0) and 0.0 < y < 1.0)
            or (y in (0.0, 1.0) and 0.0 < x < 1.0))


def _style_anchor(style, prefix):
    """從邊的 style 讀出 exitX/exitY（或 entryX/entryY）。沒寫就是浮動連接點。"""
    got = {}
    for axis in ('X', 'Y'):
        m = re.search(rf'{prefix}{axis}=([-\d.]+)', style)
        if not m:
            return None
        got[axis] = float(m.group(1))
    return (got['X'], got['Y'])


def unpinned_edges(edges):
    """端點沒有固定在四個基本錨點上的邊。

    矩形的錨點是邊界中點、菱形的是頂點——兩者都是 (0.5,0)/(1,0.5)/(0.5,1)/(0,0.5)，
    因為菱形內接於它的方框。沒指定 exitX/entryX 時 mxGraph 用浮動連接點，
    落點會偏離邊界中點，看起來就是「線沒接在框上」。
    """
    bad = []
    for e in edges:
        for prefix, where in (('exit', '起點'), ('entry', '終點')):
            a = _style_anchor(e['style'], prefix)
            if a is None:
                bad.append((e, where, '沒有固定錨點'))
            elif not _on_a_side(a):
                bad.append((e, where, f'錨點 {a} 沒有貼在邊界上'))
    return bad


def anchor_kinks(edges, nodes, tol=0.5):
    """錨點與緊鄰它的繞線點沒有共用 x 或 y 的邊。

    這是「線沒接好」的真正成因：draw.io 會在形狀旁邊補一小段折線把兩者接起來，
    看起來就是多一個小勾、或線好像沒對準邊界中點。
    """
    bad = []
    for e in edges:
        if not e['waypoints']:
            continue
        for prefix, where, nid, wp in (
            ('exit', '起點', e['src'], e['waypoints'][0]),
            ('entry', '終點', e['dst'], e['waypoints'][-1]),
        ):
            a = _style_anchor(e['style'], prefix)
            if a is None:
                continue                        # 沒錨點的另由 unpinned_edges 回報
            n = nodes[nid]
            ax, ay = n['x'] + n['w'] * a[0], n['y'] + n['h'] * a[1]
            if abs(ax - wp[0]) > tol and abs(ay - wp[1]) > tol:
                bad.append((e, where))
    return bad


def off_grid_nodes(nodes, grid=10):
    """座標沒對齊格線的節點。對齊格線後，同一欄的錨點才會落在同一條線上。"""
    return [nid for nid, n in nodes.items()
            if any(abs(v - round(v / grid) * grid) > 0.01
                   for v in (n['x'], n['y'], n['w'], n['h']))]


def _node_type(style):
    if 'swimlane' in style:
        return 'table'
    if 'shape=partialRectangle' in style:
        return 'tablerow'
    if 'ellipse' in style:
        return 'terminal'
    if 'rhombus' in style:
        return 'decision'
    if 'fillColor=none' in style and 'dashed=1' in style:
        return 'container'
    if 'align=left' in style and 'verticalAlign=top' in style:
        return 'entity'
    return 'box'


def diagram_kind(path, nodes):
    name = os.path.basename(path)
    if '_er' in name or any(n['type'] in ('entity', 'table') for n in nodes.values()):
        return 'er'
    if '_architecture' in name or any(n['type'] == 'container' for n in nodes.values()):
        return 'architecture'
    if '_flow' in name or any(n['type'] == 'decision' for n in nodes.values()):
        return 'flow'
    return 'class'


# --------------------------------------------------------------------------
# 幾何：路徑推導與交叉偵測
# --------------------------------------------------------------------------

def _center(n):
    return (n['x'] + n['w'] / 2, n['y'] + n['h'] / 2)


def _exit_point(rect, ref):
    """從 rect 往 ref 方向離開時的邊界點，取最接近 ref 的那一邊的中點投影。
    模擬 mxGraph orthogonalEdgeStyle 未指定 exitX/entryX 時的行為。"""
    cx, cy = _center(rect)
    dx, dy = ref[0] - cx, ref[1] - cy
    pad = 6
    if abs(dx) * rect['h'] > abs(dy) * rect['w']:
        x = rect['x'] + rect['w'] if dx > 0 else rect['x']
        y = min(max(ref[1], rect['y'] + pad), rect['y'] + rect['h'] - pad)
        return (x, y)
    y = rect['y'] + rect['h'] if dy > 0 else rect['y']
    x = min(max(ref[0], rect['x'] + pad), rect['x'] + rect['w'] - pad)
    return (x, y)


def _anchor_xy(node, frac):
    return (node['x'] + node['w'] * frac[0], node['y'] + node['h'] * frac[1])


def _axis(frac):
    """錨點所在的邊決定線離開/進入的方向：上下 → 垂直，左右 → 水平。"""
    return 'v' if frac[0] == 0.5 else 'h'


def _orthogonalize(pts, first_axis, last_axis):
    """把折線補成全正交：任何一段同時變動 x 與 y 就插一個轉角。
    兩端必須沿著錨點所在邊的法線方向離開／進入，中間交替。"""
    out = [pts[0]]
    axis = first_axis
    for i in range(1, len(pts)):
        px, py = out[-1]
        qx, qy = pts[i]
        if abs(px - qx) < 0.5 or abs(py - qy) < 0.5:
            out.append((qx, qy))
            axis = 'h' if abs(py - qy) < 0.5 else 'v'
            continue
        if i == len(pts) - 1:
            out.append((qx, py) if last_axis == 'v' else (px, qy))
        else:
            out.append((px, qy) if axis == 'v' else (qx, py))
            axis = 'h' if axis == 'v' else 'v'
        out.append((qx, qy))
    return out


def edge_path(edge, nodes):
    """把一條邊還原成 draw.io 實際會畫的正交折線。

    有固定錨點就從錨點出發／進入（這正是我們要的：矩形邊界中點、菱形頂點）；
    沒有錨點的舊檔退回用投影法估一個邊界點。
    """
    src, dst = nodes[edge['src']], nodes[edge['dst']]
    wps = list(edge['waypoints'])
    ex = _style_anchor(edge.get('style', ''), 'exit')
    en = _style_anchor(edge.get('style', ''), 'entry')

    if ex and en:
        start, end = _anchor_xy(src, ex), _anchor_xy(dst, en)
        return _orthogonalize([start] + wps + [end], _axis(ex), _axis(en))

    if wps:
        return [_exit_point(src, wps[0])] + wps + [_exit_point(dst, wps[-1])]
    scx, scy = _center(src)
    dcx, dcy = _center(dst)
    if abs(dcy - scy) >= abs(dcx - scx):
        start = _exit_point(src, (scx, dcy))
        end = _exit_point(dst, (dcx, scy))
        mid = (start[1] + end[1]) / 2
        return [start, (start[0], mid), (end[0], mid), end]
    start = _exit_point(src, (dcx, scy))
    end = _exit_point(dst, (scx, dcy))
    mid = (start[0] + end[0]) / 2
    return [start, (mid, start[1]), (mid, end[1]), end]


def _segments(path):
    return [(path[i], path[i + 1]) for i in range(len(path) - 1)
            if path[i] != path[i + 1]]


def _crosses(a, b):
    """兩條軸對齊線段是否真的交叉（端點相接不算）。"""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    a_vert, b_vert = ax1 == ax2, bx1 == bx2
    if a_vert == b_vert:
        return False                      # 同向線段：重疊另計，這裡不算交叉
    if b_vert:
        a, b = b, a
        (ax1, ay1), (ax2, ay2) = a
        (bx1, by1), (bx2, by2) = b
    x = ax1
    ylo, yhi = sorted((ay1, ay2))
    xlo, xhi = sorted((bx1, bx2))
    y = by1
    return xlo < x < xhi and ylo < y < yhi


def count_crossings(edges, nodes):
    paths = [(e, _segments(edge_path(e, nodes))) for e in edges]
    pairs = []
    for i in range(len(paths)):
        ei, si = paths[i]
        for j in range(i + 1, len(paths)):
            ej, sj = paths[j]
            if {ei['src'], ei['dst']} & {ej['src'], ej['dst']}:
                continue                  # 共用端點的兩條邊在節點旁相會，不是交叉
            if any(_crosses(a, b) for a in si for b in sj):
                pairs.append((ei, ej))
    return pairs


ROUND_SHAPES = {'decision', 'terminal'}      # 菱形、橢圓：只有四個中點碰得到形狀


def shared_vertex_reason(a, b, nodes):
    """兩條線重疊時，如果原因是「接在同一個菱形/橢圓的同一個頂點」就指出來。

    矩形可以把同一側的多個錨點沿邊分散開；菱形與橢圓不行——分散後的點會落在
    框線外的空白處，箭頭就浮在半空。所以這兩種形狀的同一個頂點只能接一條線，
    多出來的要改接別的邊，而不是把錨點推開。
    """
    shared = ({a['src'], a['dst']} & {b['src'], b['dst']})
    for nid in shared:
        if nodes[nid]['type'] in ROUND_SHAPES:
            return (f'兩條線接在 {nid} 的同一個頂點；'
                    f'菱形/橢圓的錨點無法沿邊分散，要改接不同的邊')
    return None


def _run_overlap(a, b, tol=1.0):
    """兩條同向線段的共線重疊區間；沒有重疊回傳 None。"""
    (ax1, ay1), (ax2, ay2) = a
    (bx1, by1), (bx2, by2) = b
    a_vert, b_vert = abs(ax1 - ax2) < tol, abs(bx1 - bx2) < tol
    if a_vert != b_vert:
        return None
    if a_vert:
        if abs(ax1 - bx1) > tol:
            return None
        lo = max(min(ay1, ay2), min(by1, by2))
        hi = min(max(ay1, ay2), max(by1, by2))
        return ((ax1, lo), (ax1, hi)) if hi - lo > 0 else None
    if abs(ay1 - by1) > tol:
        return None
    lo = max(min(ax1, ax2), min(bx1, bx2))
    hi = min(max(ax1, ax2), max(bx1, bx2))
    return ((lo, ay1), (hi, ay1)) if hi - lo > 0 else None


def overlapping_runs(edges, nodes, min_len=8.0, tol=1.0):
    """共線重疊的線段對——兩條線疊在一起畫，讀者只看得到一條。

    交叉是一個點，看得出來是兩條線各走各的；重疊是一整段，兩條線變成同一條，
    這比交叉嚴重得多。唯一容許的例外是**共用端點的線在那個端點旁邊的短樁**：
    從同一個錨點出發的線本來就得先重合一小段才能分開，那是同一束線的一部分，
    但要盡早分岔，別讓它們並行整段路。
    """
    paths = [(e, _segments(edge_path(e, nodes))) for e in edges]
    bad = []
    for i in range(len(paths)):
        ei, si = paths[i]
        for j in range(i + 1, len(paths)):
            ej, sj = paths[j]
            worst = None
            for a in si:
                for b in sj:
                    run = _run_overlap(a, b, tol)
                    if not run:
                        continue
                    length = math.dist(run[0], run[1])
                    if length <= min_len:
                        continue
                    if worst is None or length > worst:
                        worst = length
            if worst:
                bad.append((ei, ej, worst))
    return bad


def count_line_over_box(edges, nodes):
    """線穿過第三個方框（= 畫在別人的文字上）。container 只算頂部標題帶。"""
    hits = []
    for e in edges:
        segs = _segments(edge_path(e, nodes))
        skip = kin_of(e['src'], nodes) | kin_of(e['dst'], nodes)
        for nid, n in nodes.items():
            if nid in skip:
                continue
            h = min(n['h'], 26) if n['type'] == 'container' else n['h']
            x0, y0, x1, y1 = n['x'], n['y'], n['x'] + n['w'], n['y'] + h
            for (sx, sy), (ex, ey) in segs:
                if sx == ex and x0 <= sx <= x1 and min(sy, ey) < y1 and max(sy, ey) > y0:
                    hits.append((e, nid))
                    break
                if sy == ey and y0 <= sy <= y1 and min(sx, ex) < x1 and max(sx, ex) > x0:
                    hits.append((e, nid))
                    break
            else:
                continue
            break
    return hits


def direction_stats(edges, nodes):
    """統計邊的方向。回頭線（往上）是版面警訊，除非它就是刻意的迴圈。"""
    stats = {'down': 0, 'up': 0, 'side': 0}
    back_edges = []
    for e in edges:
        s, d = _center(nodes[e['src']]), _center(nodes[e['dst']])
        dy, dx = d[1] - s[1], d[0] - s[0]
        if abs(dy) <= max(nodes[e['src']]['h'], nodes[e['dst']]['h']) / 2:
            stats['side'] += 1
        elif dy > 0:
            stats['down'] += 1
        else:
            stats['up'] += 1
            back_edges.append(e)
    return stats, back_edges


def waypoints_inside_own_box(edges, nodes):
    """繞線點落在自己來源／目標方框裡的邊：線會從框內畫出來，看起來像穿過自己。
    「線壓到方框」的檢查會把來源與目標排除掉，所以這種錯誤那邊抓不到。"""
    bad = []
    for e in edges:
        for nid in (e['src'], e['dst']):
            n = nodes[nid]
            for (px, py) in e['waypoints']:
                if n['x'] < px < n['x'] + n['w'] and n['y'] < py < n['y'] + n['h']:
                    bad.append((e, nid))
                    break
    return bad


def orphans(nodes, edges):
    """沒有任何連線的節點。多半是打錯 id 或畫到一半忘了接——
    交付前檢查清單第 5 條：每個元素至少有一條線連著，否則它為什麼在這張圖。

    兩種例外：container 是純視覺邊界，本來就不接線；資料表的欄位列絕大多數
    沒有外鍵，逐列檢查沒有意義——改成「只要有任一欄位接了線，這張表就算連上」，
    這樣仍抓得到「整張表跟誰都沒關係」這個真正值得知道的問題。"""
    connected = set()
    for e in edges:
        for nid in (e['src'], e['dst']):
            connected.add(nid)
            parent = nodes[nid].get('parent', '1')
            if parent in nodes:
                connected.add(parent)
    return [nid for nid, n in nodes.items()
            if nid not in connected and n['type'] not in ('container', 'tablerow')]


def bbox(nodes, edges):
    xs, ys, xe, ye = [], [], [], []
    for n in nodes.values():
        xs.append(n['x']); ys.append(n['y'])
        xe.append(n['x'] + n['w']); ye.append(n['y'] + n['h'])
    for e in edges:
        for (px, py) in e['waypoints']:
            xs.append(px); ys.append(py); xe.append(px); ye.append(py)
    if not xs:
        return 0, 0, 0, 0
    return min(xs), min(ys), max(xe), max(ye)


# --------------------------------------------------------------------------
# 建議
# --------------------------------------------------------------------------

def suggest(aspect, w, h, n_nodes):
    """把「太寬／太高」換算成具體動作，而不是只丟一個數字。"""
    out = []
    if aspect > ASPECT_MAX:
        cols_now = max(1, round(math.sqrt(n_nodes * aspect)))
        out.append(
            f"太寬（{aspect:.2f} > {ASPECT_MAX}）：找出最寬的一排，把其中並排的元素改成上下堆疊。"
            f"目前約 {cols_now} 欄，往 {max(1, cols_now - 1)} 欄收。"
        )
    elif aspect < ASPECT_MIN:
        need = math.sqrt(ASPECT_MIN / aspect) if aspect else 2
        cols = max(2, math.ceil(need))
        out.append(
            f"太高（{aspect:.2f} < {ASPECT_MIN}）：折成 {cols} 欄蛇形——"
            f"主幹往下走到約 y={int(h / cols)} 就跨到右邊一欄繼續往下。"
            f"預估折完長寬比可到 {aspect * cols:.2f}。"
        )
    return out


# --------------------------------------------------------------------------
# PlantUML
# --------------------------------------------------------------------------

def measure_puml(path):
    """渲染 .puml 並讀出 PNG 尺寸。回傳 (w, h) 或 None（沒有渲染環境）。"""
    cmd = None
    if shutil.which('plantuml'):
        cmd = ['plantuml', '-tpng', '-o', os.path.dirname(os.path.abspath(path)) or '.', path]
    else:
        jar = os.environ.get('PLANTUML_JAR')
        if jar and os.path.exists(jar) and shutil.which('java'):
            cmd = ['java', '-jar', jar, '-tpng', path]
    if not cmd:
        return None
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError):
        return None
    png = os.path.splitext(path)[0] + '.png'
    if not os.path.exists(png):
        return None
    with open(png, 'rb') as fh:
        head = fh.read(24)
    if head[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    return int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')


# --------------------------------------------------------------------------
# 報告
# --------------------------------------------------------------------------

def check_drawio(path, verbose=True):
    nodes, edges = parse_drawio(path)
    if not nodes:
        print(f'{os.path.basename(path)}: 沒有節點，跳過')
        return True

    x0, y0, x1, y1 = bbox(nodes, edges)
    w, h = x1 - x0, y1 - y0
    aspect = w / h if h else 0
    kind = diagram_kind(path, nodes)
    cap = ELEMENT_CAPS.get(kind, 20)
    countable = [n for n in nodes.values()
                 if n['type'] not in ('container', 'tablerow')]

    crossings = count_crossings(edges, nodes)
    over_box = count_line_over_box(edges, nodes)
    stats, back_edges = direction_stats(edges, nodes)
    lonely = orphans(nodes, edges)
    inside = waypoints_inside_own_box(edges, nodes)
    unpinned = unpinned_edges(edges)
    overlaps = overlapping_runs(edges, nodes)
    kinks = anchor_kinks(edges, nodes)
    off_grid = off_grid_nodes(nodes)

    ok = (ASPECT_MIN <= aspect <= ASPECT_MAX) and not crossings and not over_box \
        and not lonely and not inside and not unpinned and not kinks \
        and not off_grid and not overlaps and len(countable) <= cap
    mark = 'PASS' if ok else 'FAIL'

    print(f'\n{mark}  {os.path.basename(path)}  [{kind}]')
    print(f'  尺寸 {w:.0f}×{h:.0f}   長寬比 {aspect:.2f}   '
          f'節點 {len(countable)}/{cap}   連線 {len(edges)}')
    print(f'  方向 ↓{stats["down"]} ↑{stats["up"]} ↔{stats["side"]}   '
          f'交叉 {len(crossings)}   壓到方框 {len(over_box)}   孤立 {len(lonely)}')
    print(f'  接點 未固定 {len(unpinned)}   歪接 {len(kinks)}   未對齊格線 {len(off_grid)}'
          f'   線重疊 {len(overlaps)}')

    if not verbose:
        return ok

    for line in suggest(aspect, w, h, len(countable)):
        print(f'  → {line}')
    for a, b, length in overlaps[:8]:
        why = shared_vertex_reason(a, b, nodes) or '兩條線疊成一條，只能交叉於一點'
        print(f'  ✗ 線重疊 {length:.0f}px：{a["src"]}→{a["dst"]} 與 {b["src"]}→{b["dst"]}'
              f'（{why}）')
    if len(overlaps) > 8:
        print(f'    …另有 {len(overlaps) - 8} 組重疊')
    for e, where, why in unpinned[:6]:
        print(f'  ✗ 接點未固定：{e["src"]}→{e["dst"]} 的{where}{why}')
    if len(unpinned) > 6:
        print(f'    …另有 {len(unpinned) - 6} 個接點未固定')
    for e, where in kinks[:6]:
        print(f'  ✗ 歪接：{e["src"]}→{e["dst"]} 的{where}與相鄰繞線點不共線（會多一個小勾）')
    if off_grid:
        print(f'  ✗ 未對齊格線（10px）：{", ".join(off_grid[:8])}'
              + ('…' if len(off_grid) > 8 else ''))
    for e, nid in inside:
        print(f'  ✗ 繞線點在 {nid} 自己的方框裡：{e["src"]}→{e["dst"]}（線會從框內畫出來）')
    for nid in lonely:
        print(f'  ✗ 孤立節點：{nid}（沒有任何連線——是漏接還是根本不該在這張圖）')
    if len(countable) > cap:
        print(f'  → 節點 {len(countable)} 個超過 {kind} 的上限 {cap}，先考慮拆圖再談排版')
    for a, b in crossings[:8]:
        print(f'  ✗ 交叉：{a["src"]}→{a["dst"]} 與 {b["src"]}→{b["dst"]}')
    if len(crossings) > 8:
        print(f'    …另有 {len(crossings) - 8} 組交叉')
    for e, nid in over_box[:8]:
        print(f'  ✗ 壓框：{e["src"]}→{e["dst"]} 穿過 {nid}')
    if len(over_box) > 8:
        print(f'    …另有 {len(over_box) - 8} 條壓框')
    for e in back_edges[:5]:
        label = e['label'] or '(無標籤)'
        print(f'  ↑ 往上的邊：{e["src"]}→{e["dst"]} {label}'
              f'（該是刻意的迴圈或蛇形跨欄，不該是隨手接上去的）')
    return ok


def check_puml(path):
    size = measure_puml(path)
    if size is None:
        print(f'\nSKIP  {os.path.basename(path)}')
        print('  沒有 plantuml/java 可渲染，無法量測。'
              '貼到 https://www.plantuml.com/plantuml 或 https://kroki.io 目視確認，'
              '不要當成已驗證。')
        return True
    w, h = size
    aspect = w / h if h else 0
    ok = ASPECT_MIN <= aspect <= ASPECT_MAX
    print(f'\n{"PASS" if ok else "FAIL"}  {os.path.basename(path)}')
    print(f'  尺寸 {w}×{h}   長寬比 {aspect:.2f}   面積 {w * h / 1000:.0f}k')
    src = open(path, encoding='utf-8').read()
    n_nodes = len(re.findall(r'^\s*(?:class|interface|entity|abstract|participant|actor|state)\b',
                             src, re.M))
    for line in suggest(aspect, w, h, max(n_nodes, 1)):
        print(f'  → {line}')
    return ok


def main(argv):
    paths = [p for p in argv[1:] if not p.startswith('-')]
    if not paths:
        print(__doc__)
        return 2
    all_ok = True
    for p in paths:
        if not os.path.exists(p):
            print(f'找不到檔案：{p}')
            all_ok = False
            continue
        if p.endswith('.drawio'):
            all_ok &= check_drawio(p)
        elif p.endswith(('.puml', '.plantuml', '.pu')):
            all_ok &= check_puml(p)
        else:
            print(f'不支援的副檔名：{p}（要 .drawio / .puml）')
            all_ok = False
    print()
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
