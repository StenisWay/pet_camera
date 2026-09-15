---
name: drawio-flowchart
description: Generate a validated draw.io (.drawio) diagram — an activity/flowchart from a functional spec (rule_doc/功能需求/0X_spec_*.md), an ER/schema diagram from the data-model doc, or a system/component architecture diagram from the PRD — saved into rule_doc/功能需求/diagrams/. Use when asked to draw, create, or update a flow diagram / UML diagram / flowchart / ER diagram / DB schema diagram / architecture diagram / component diagram / system diagram / 程式架構圖.
---

# Spec → draw.io flowchart

Turns a functional spec's "功能說明" (behavior steps) and "錯誤碼" (error code) sections into
a draw.io activity diagram, via a small Python DSL instead of hand-written XML — hand-writing
mxGraph XML is slow and error-prone (duplicate ids, dangling edges); the generator in this
skill folder (`drawio_gen.py`) catches those mistakes at build time instead of leaving a
silently-broken file.

## When to use

The user asks for a flow diagram / UML diagram / flowchart for a specific feature, or for
"all functions" (in which case repeat this process once per functional spec file under
`rule_doc/功能需求/0X_spec_*.md` — not the PRD, not the data-model doc, not the cross-cutting
error-handling doc). Also use this generator for an ER/DB-schema diagram from the data-model
doc, or a system/component architecture diagram from the PRD's 系統架構 section — see the
matching sections further down; each is a different node-type vocabulary but the same
generator, validation process, and "don't hand-write XML" reasoning.

## Process (activity/flowchart diagrams)

1. **Read the target spec file(s)** in `rule_doc/功能需求/`. Pull out:
   - The numbered steps under "功能說明" / "2.x" sections → these become the main flow spine.
   - Every "X 是否 / X 成立?" style condition → a `decision` node.
   - The "錯誤碼" table → one `error` node per row that represents a terminal failure reachable
     from a decision branch (not every error code needs a node — only ones that are a distinct
     branch outcome in the flow, e.g. skip purely-informational codes like offline-state display).
   - Cross-platform differences (see e.g. `02_spec_登入註冊與密碼重設.md` 平台差異 tables) → split
     into parallel branches from a `decision` node, not two separate diagrams.

2. **Design the node/edge list before writing any XML.** Lay out a plan like:
   ```
   start -> step1 -> decision(条件?) --否--> error(CODE) [end of that branch]
                                     --是--> step2 -> ... -> end
   ```
   Keep one linear "spine" down the main column and push side branches (errors, alternate
   platform paths) to the side in x, at the same y as the decision that produces them.

3. **Write a throwaway generator script** (in your scratchpad, not in the repo) that imports
   the library in this skill folder and calls `build()`:
   ```python
   import importlib.util
   spec = importlib.util.spec_from_file_location(
       "drawio_gen", "<repo>/.claude/skills/drawio-flowchart/drawio_gen.py")
   dg = importlib.util.module_from_spec(spec); spec.loader.exec_module(dg)

   nodes = [dg.n('start', '開始', 'start', x=380, y=0, w=160, h=50), ...]
   edges = [dg.e('start', 'p1'), ...]
   xml = dg.build('<診斷圖標題>', nodes, edges, page_w=..., page_h=...)
   open('rule_doc/功能需求/diagrams/<NN>_flow_<spec-name>.drawio', 'w', encoding='utf-8').write(xml)
   ```
   `build()` already raises immediately on a duplicate node id or an edge pointing at a
   node that doesn't exist — fix those before moving on, don't suppress the error.

   Node/edge id rule: never name a node `e<digits>` (e.g. `e1`) — edge ids are
   auto-generated as `e0, e1, e2, ...` and a collision silently corrupts the file. Prefix
   error/note node ids distinctly (`err1`, `noteWeb`, ...).

4. **Naming and location convention** (matches the rest of `rule_doc/功能需求/`):
   - File: `rule_doc/功能需求/diagrams/<same-two-digit-prefix-as-the-spec>_flow_<spec-name-without-"spec_">.drawio`
     e.g. `07_spec_事件偵測與自動錄影.md` → `diagrams/07_flow_事件偵測與自動錄影.drawio`.
   - One diagram per functional spec file (F0.1–F0.4, F1–F6 style features). Don't diagram the
     PRD or the shared error/state-handling doc — those aren't flows. The data-model doc gets an
     ER diagram instead (see below), not an activity diagram.
   - Flow diagrams are **not** split by App/Web the way screen specs are (see `rule-doc-writer`
     skill) — behavior is defined once in the functional spec; where App/Web genuinely branch
     (e.g. login's token issuance), represent that as a `decision` node with two labelled edges
     inside the *same* diagram, not two separate files.

4.5. **Pin the line endpoints, then align the waypoints to them.** `build()` writes
   `exitX/exitY/entryX/entryY` on every edge for you, choosing the side from the geometry
   (first waypoint decides where the line leaves the source, last one where it enters the
   target). A lone edge gets that side's midpoint — `(0.5,0)` `(1,0.5)` `(0.5,1)` `(0,0.5)`,
   which are a rectangle's edge midpoints and, on a rhombus, exactly its corners, so one
   rule covers both shapes. Without pinned anchors mxGraph uses a floating connection whose
   landing point drifts off the midpoint, and the line visibly fails to meet the box.

   When several edges attach to the **same side of the same node**, `assign_anchors()`
   spreads them along that side (k edges → `1/(k+1)`, `2/(k+1)`, …), ordered by where each
   one is heading so they don't cross right next to the node. Sharing one anchor point
   would make those edges leave from the same point in the same direction and run exactly
   on top of each other until they diverge — one column linking to two tables has to read
   as two lines, not one. Entering and leaving edges count together on a side.

   Spreading only applies to shapes whose sides are real edges — that's the `SPREADABLE`
   set (rectangles, tables, rows, containers). A **rhombus** (`decision`) and an **ellipse**
   (`start`/`end`) only touch their bounding box at the four side midpoints, so `(0.33, 0)`
   on a diamond lands in empty space above the shape and the arrowhead floats there,
   attached to nothing. Those shapes get one edge per vertex; a second edge wanting the
   same vertex has to **enter through a different vertex** instead (a retry loop usually
   takes whichever side is still free, going the long way round if needed). A diamond has
   exactly four attachment points — one incoming plus four outgoing does not fit, and that
   case has to be restructured or flagged as a known exception.

   Anchors alone are not enough: a waypoint that shares neither x nor y with its anchor
   makes mxGraph insert a dog-leg right at the shape (the "line has a gap / a little hook"
   defect). So before building, call `dg.align_waypoints(nodes, edges)` — it nudges each
   edge's first/last waypoint onto the anchor's axis — then `dg.check_kinks(nodes, edges)`
   to confirm none are left. `align_waypoints` moves geometry, so run `check_overlaps`
   *after* it, not before.

   Keep node geometry on the grid while you are at it: x/y in multiples of 10 and **width
   and height in multiples of 20**. A center is `x + w/2`, so only an even-multiple-of-20
   width puts the center back on the grid — that is what makes the anchors of differently
   sized nodes in one column line up, and a vertical spine render as one straight line
   instead of a staircase.

5. **Validate every file you touch**, even ones you believe are unchanged. Two separate
   checks, both required — one does not substitute for the other:
   - `dg.validate_file(path)` — structural: well-formed XML, no duplicate ids, no dangling edges.
   - `dg.check_overlaps(nodes, edges)` — **call this on the node/edge lists before you even
     write the file**, not after. A file can be structurally perfect and still render with
     lines drawn straight over other nodes' text — that's a real defect, not a nitpick (this
     happened across multiple diagrams in this project before the checker existed: a login
     flow with four side-by-side branches, a streaming flow's retry loop-back, and a whole
     architecture diagram's fan-out edges all had lines cutting through unrelated labels).
     See "Routing edges around obstacles" below for how to fix what it finds.
   ```bash
   cd rule_doc/功能需求/diagrams && for f in *.drawio; do python3 -c "
   import sys; sys.path.insert(0, '<repo>/.claude/skills/drawio-flowchart')
   import drawio_gen as dg
   problems = dg.validate_file('$f')
   print('$f', 'OK' if not problems else 'FAIL: ' + str(problems))
   "; done
   ```
   Do not report the task done until every file prints `OK` **and** `check_overlaps()` and
   `check_kinks()` both returned empty for every diagram you touched.

   Those three cover structure and line-vs-box collisions. They say nothing about whether
   the diagram is *shaped* well — aspect ratio, crossing lines, orphan nodes, grid
   alignment. That's the `uml-diagram` skill's job; run its checker too:
   ```bash
   python3 .claude/skills/uml-diagram/scripts/check_layout.py rule_doc/功能需求/diagrams/*.drawio
   ```

6. **Update the SDLC matrix.** After adding or renaming a diagram file, the "UML流程圖" column
   in `rule_doc/99_SDLC矩陣圖.md` must point at it — see the `sdlc-matrix` skill for how that
   file is maintained; don't hand-edit it out of sync with this one.

## ER / DB-schema diagrams

For "draw the DB schema" style requests, use `dg.table()`. It emits a table box plus one
child cell per column, so a foreign key can be drawn **from the column to the column** —
`users.id` into `devices.user_id` — instead of from box to box:

```python
nodes = []
nodes += dg.table('users', 'users', [
    ('PK', 'id : uuid'), ('', 'email : text (unique)'), ...], x=60, y=0, w=300)
nodes += dg.table('devices', 'devices', [
    ('PK', 'id : uuid'), ('FK', 'user_id : uuid'), ...], x=60, y=260, w=300)
edges = [dg.e('users.id', 'devices.user_id', '1—N')]
```

- Column cell ids are `<table>.<column>`, which is what makes the edge list read like the
  schema itself. `table()` returns `[table, *columns]` — keep that order when concatenating,
  a child emitted before its parent cannot resolve its parent id.
- One edge per foreign key, from the referenced column (the 1 end) to the referencing
  column (the N end), labelled with the cardinality, e.g. `1—N`.
- Column cells are children, so their geometry is parent-relative in the file; every node
  dict here keeps **absolute** coordinates and `build()` converts on the way out. If you
  write your own layout helper, carry the `parent` key through — dropping it makes a column
  look like a free-standing node and its own table gets treated as an obstacle.
- The older `entity` node type + `build_entity_label()` renders the same field list as one
  text blob. It is only worth using when the diagram genuinely does not need per-column
  edges, because those are the whole point of a schema diagram.
- Output file: `rule_doc/功能需求/diagrams/01_er_<data-model-doc-name>.drawio` (paired with
  `01_資料模型與儲存規格.md` by the same `01` prefix — there's only one of these per project,
  unlike the one-per-feature flowcharts).
- Same validation step applies — run it before calling the diagram done.

## System / component architecture diagrams

For "draw the architecture / system diagram" style requests, read the PRD's 系統架構 section
(the ASCII-art component diagram + 架構決策 bullets) as the source of truth, and use these node
types instead of the activity-diagram ones:

```python
nodes = [
    dg.n('app', '手機 App\n(iOS / Android)', 'client', x=..., y=..., w=220, h=60),
    dg.n('vm', 'Oracle Cloud VM(Docker Compose)', 'container', x=..., y=..., w=800, h=240),
    dg.n('api', 'Backend API', 'component', x=..., y=..., w=220, h=60),
    dg.n('r2', 'Cloudflare R2\n(影片/縮圖)', 'external', x=..., y=..., w=200, h=60),
]
edges = [dg.e('app', 'api', 'HTTPS / WebRTC'), ...]
```

- `client` — a client app/device the user interacts with directly (mobile app, web app, an edge
  device like a camera). Lavender.
- `component` — a piece of our own backend, deployed and maintained by us. Blue (same color as
  `process` in flowcharts — same "our code" meaning, different diagram genre).
- `external` — a third-party service we depend on but don't run (object storage, a TURN
  provider, push notification gateways, an OAuth'd external API). Grey.
- `container` — a dashed boundary box representing one deployment host/environment (e.g. one
  VM running several components via Docker Compose). **Add it to the `nodes` list before the
  components it contains**, not after — later nodes render on top in mxGraph's z-order, so the
  boundary must come first or it'll visually cover its own contents.
- Edges get labelled with the protocol/purpose (`HTTPS / WebRTC`, `RTSP 攝影機串流`, `localhost`,
  `WebRTC signaling`, `OAuth + 上傳`), not left bare — a system diagram whose arrows don't say
  *how* two things talk to each other has lost the one thing worth drawing it for.
- Output file: `rule_doc/功能需求/diagrams/00_architecture_<name>.drawio` — `00` prefix, paired
  with the PRD (which is also `00_`), one per project, not one per feature.
- Same validation step applies.

## Routing edges around obstacles (avoiding lines-over-text)

`dg.check_overlaps(nodes, edges, margin=6)` approximates whether an edge's routed path
would cross a *third* node's box (not its own source/target). For each edge without explicit
waypoints it tries both natural Manhattan routings (horizontal-then-vertical and
vertical-then-horizontal) between the source and target centers, and only flags a problem if
**both** fail — i.e. no sane auto-router could avoid the obstacle either way, so you need to
take over the routing yourself. `container`-type nodes are treated specially: since they're
hollow boundary boxes whose only text is a title strip at the top (`CONTAINER_LABEL_BAND`,
~26px), only that strip counts as an obstacle — edges are expected to pass through the rest of
a container freely, that's the point of drawing one.

When it flags an edge, fix it with one of these, roughly in order of how often each one is
actually the right call:

1. **Add breathing room.** Most overlaps are a spacing problem, not a routing problem — two
   parallel branches (e.g. four side-by-side flows in a login diagram: register / login /
   forgot-password / logout) placed too close together so one branch's error box lands in the
   next branch's column. Widen the gap between columns until `check_overlaps` stops
   complaining; this fixed 7 of 8 problems found in this project's diagrams. A rule of thumb:
   leave at least 250–300px of *dead* horizontal space between a branch's rightmost element
   (including its side error boxes) and the next branch's leftmost element.

2. **Give it explicit waypoints** when the two nodes are legitimately far apart with real
   obstacles between them no matter how you space things (e.g. a retry loop jumping back
   several rows up, or a client node that must reach a component buried inside a container).
   Pass `dg.e(src, dst, label, waypoints=[(x1,y1), (x2,y2), ...])` — `build()` renders these as
   an explicit `points` array so the rendered edge follows exactly this polyline, not
   whatever mxGraph's auto-router would otherwise pick. **Every segment must be axis-aligned**
   (each waypoint shares either the x or the y of the point before it) — `check_overlaps` only
   detects collisions on horizontal/vertical segments; a diagonal segment is a blind spot that
   silently passes the checker without actually being checked.

3. **Route through a shared corridor/bus** when several edges need to get from one cluster to
   another past the same obstacles (e.g. multiple replicated services all reaching the same
   external dependencies below them). Pick an x that's genuinely clear top-to-bottom — usually
   the gap between two containers, or just outside the outermost one — drop onto it, travel
   along a shared horizontal "bus" y that's genuinely clear left-to-right — usually the gap
   between two rows of components — then rise into the target. A small helper function local
   to your generator script keeps this from turning into repetitive coordinates:
   ```python
   def to_bus(src_id, dst_id, label, corridor_x=MID_CORRIDOR_X):
       return dg.e(src_id, dst_id, label, waypoints=[
           (corridor_x, cy(src_id)), (corridor_x, BUS_Y), (cx(dst_id), BUS_Y),
       ])
   ```
   Watch out for sources that sit *between* the obstacle and the corridor — e.g. if node A is
   left of node B and both need the same corridor, A's own straight line out to that corridor
   will cut through B unless A uses a corridor on the *other* side instead. This is the one
   case in this project that "add breathing room" alone didn't fix — check which side of your
   obstacles each source actually sits on, not just whether a corridor exists.

## Style reference

| Semantic meaning in the spec | Node type | Notes |
|---|---|---|
| Flow entry / exit | `start` / `end` | green ellipse |
| A step, API call, or state transition | `process` | blue rectangle |
| A branch ("X 有效?", "X 成立?") | `decision` | yellow rhombus, label ends in `?` |
| A terminal error-code outcome | `error` | red rounded rect, label = `"<CODE>\n<short message>"` |
| Background/async behavior or a cross-reference, not a step the user waits on | `note` | dashed grey box |
| A DB table in an ER diagram | `entity` | white box, left-aligned field list via `build_entity_label` |
| A client app/device (architecture diagram) | `client` | lavender rectangle |
| Our own backend component (architecture diagram) | `component` | blue rectangle |
| A third-party/external service (architecture diagram) | `external` | grey rectangle |
| A deployment host boundary (architecture diagram) | `container` | dashed, unfilled — add before its contents |

Keep vertical spacing around 100–120px between stacked steps and roughly 200–260px between
side-by-side branch columns so orthogonal edges don't overlap adjacent columns.
