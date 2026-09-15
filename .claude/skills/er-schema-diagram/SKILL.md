---
name: er-schema-diagram
description: "畫或更新關聯式資料庫綱要圖（schema/ER 圖）——欄位層級的外鍵連線，線從 users.id 接到 devices.user_id，而不是從表格接到表格。使用者說「畫 ER 圖」「畫資料庫關聯圖」「畫 schema 圖」「畫資料表關聯」「table 跟 schema 的關聯圖」「更新資料模型圖」，或改了 rule_doc/功能需求/01_資料模型與儲存規格.md 之後要同步圖，都用這個 skill。也用於檢查既有 ER 圖是否漏表、外鍵是否接在欄位上、線有沒有重疊。純流程圖用 drawio-flowchart，版面通則用 uml-diagram。"
---

# 關聯式綱要圖（欄位層級的 ER 圖）

一條從 `users` 方框拉到 `devices` 方框的線，只說得出「這兩張表有關係」。
一條從 `users.id` 那一列拉到 `devices.user_id` 那一列的線，說得出**是哪個欄位參照哪個
欄位**——讀者要據此寫 migration 或 join，只有後者夠用。這個 skill 就是在講怎麼畫出後者。

## 來源與範圍

- **唯一來源**：`rule_doc/功能需求/01_資料模型與儲存規格.md` 第 2 節。欄位、型別、
  nullable、外鍵指向全部從那裡讀，不要從舊圖抄——舊圖可能已經落後。
- **輸出**：`rule_doc/功能需求/diagrams/01_er_資料模型.drawio`（一個專案一張，`01` 前綴
  對應資料模型文件）。
- **每一張表都要畫**，包含沒有被別人參照的表。畫完拿文件的 `###` 小節清單逐一核對——
  這個專案曾經漏掉 `push_tokens`，圖上看不到的表，讀者會以為它不存在。

## 結構：表格是容器，欄位是子格

用 `drawio-flowchart` skill 的 `dg.table()`，不要用 `dg.n(..., 'entity')`：

```python
nodes = []
nodes += dg.table('users', 'users', [
    ('PK', 'id : uuid'),
    ('',   'email : text (unique)'),
    ('',   'created_at : timestamptz'),
], x=60, y=0, w=300)
nodes += dg.table('devices', 'devices', [
    ('PK', 'id : uuid'),
    ('FK', 'user_id : uuid'),
    ('',   'status : text'),
], x=60, y=260, w=300)

edges = [dg.e('users.id', 'devices.user_id', '1—N')]
```

- 欄位格的 id 是 `<表>.<欄位>`，所以邊的列表讀起來就是 schema 本身。
- `table()` 回傳 `[表格, *欄位格]`，串接時保持這個順序：子格排在父表之前，mxGraph
  解不到 parent。
- 欄位文字寫 `名稱 : 型別`，nullable 標 `NULL`。`PK`／`FK` 標記由 `table()` 對齊，
  欄位格用等寬字，讀者掃一眼就找得到鍵。
- 型別太長就縮寫（`timestamptz` → `ts`），不要把表格拉寬——寬度統一 300 最好對齊。

## 擺放：被參照的一方全部放同一欄

```
左欄（1 端，被參照）        右欄（N 端，參照方）
  users                      refresh_tokens
  devices                    push_tokens
  events                     media_items
```

- 左欄由上而下依參照深度排：`users` → `devices` → `events`（誰被誰參照就排在上面）。
- 這樣**所有外鍵線一律由左往右**，方向語意一致，讀者不必逐條追方向。
- 兩欄之間留 250–300px 給線道（見下一節），欄內表格上下留 40px 以上。
- 長寬比目標 0.75–1.35。表格高度 = 40 + 30×欄位數，先把六張表的高度加總再決定分欄。

## 連線：一條線一條專屬線道

**這是最容易畫壞的地方。** 規則只有三條：

1. **端點固定在欄位格的左右邊上**，只有一條線時用中點（`(1,0.5)` 出、`(0,0.5)` 進）。
   **同一個欄位連到多個地方時，錨點要沿那條邊分開**——`users.id` 連到三張表就用
   `0.25 / 0.5 / 0.75`，不要三條線擠在同一點。共用錨點的線在分岔前完全重合，
   看起來只有一條，而「同一個 key 連到兩個地方」正是 schema 圖最常見的情況。
   `dg.assign_anchors()` 會依對面那一端的位置自動分配（`dg.build()` 內部會呼叫）；
   繞線點必須與分配後的錨點共線——用 `dg.align_waypoints()` 處理，`dg.check_kinks()` 驗。
2. **每條外鍵各走一條專屬垂直線道**，線道間隔 40px。共用線道會讓兩條線疊成一條：
   交叉只是一個點，讀者看得出是兩條線；重疊是一整段，兩條線變成同一條。
   **重疊絕對不允許，交叉可以接受。**
3. **線道順序決定交叉數**：來源列越低的邊，線道排越內側（越靠左欄）。
   上方來源的水平出線段就只會經過更內側的線道，而那些線道的垂直段都在更下方，碰不到。
   反過來排會條條相交。

```python
cross = [fk for fk in FKS if b.cx(fk[0]) < b.cx(fk[1])]   # 跨欄的
cross.sort(key=lambda fk: -b.cy(fk[0]))                   # 來源越低 → 越內側
for i, fk in enumerate(cross):
    lane = left_column_right_edge + 20 + i * 40
    wp = [(lane, b.cy(fk[0])), (lane, b.cy(fk[1]))]
```

同一欄內往下的外鍵（例如 `users.id → devices.user_id`）走左外側，同樣一條一道。

**有一種交叉消不掉**：同一欄的兩條外鍵——`users.id → devices.user_id` 與
`devices.id → events.device_id`——因為 PK 列永遠在 FK 列上方，兩條線的縱向區間必然
重疊 30px 左右，不論線道怎麼排都會交叉一次。這種要在交付說明裡講清楚，不要繼續調參數。

## 基數標註

- 每條線標基數：`1—N`。
- nullable 的外鍵要標出來：`1—N (NULL 允許)`——`0..1` 跟 `1` 的差別就是實作時的 NOT NULL。
- 多對多不可以只畫一條線，要畫出中間的關聯表（本專案目前沒有）。

## 驗收

三道檢查全跑，缺一不可：

```bash
# 結構：XML 合法、沒有重複 id、沒有斷掉的邊
python3 -c "import sys; sys.path.insert(0,'.claude/skills/drawio-flowchart'); \
import drawio_gen as dg; print(dg.validate_file('rule_doc/功能需求/diagrams/01_er_資料模型.drawio'))"

# 版面：長寬比、線重疊、交叉、錨點、格線、漏接的表
python3 .claude/skills/uml-diagram/scripts/check_layout.py \
        rule_doc/功能需求/diagrams/01_er_資料模型.drawio
```

過關標準：**線重疊 0（無例外）**、接點未固定 0、歪接 0、未對齊格線 0、孤立 0、
長寬比 0.75–1.35；交叉數越少越好，剩下的要能說明為什麼消不掉。

產生腳本寫在 scratchpad，不要留在 repo 裡（跟 `drawio-flowchart` 的做法一致）。
改完圖記得同步 `rule_doc/99_SDLC矩陣圖.md` 的對應連結（見 `sdlc-matrix` skill）。
