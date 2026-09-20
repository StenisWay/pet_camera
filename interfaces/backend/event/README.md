# Event 服務(F2:事件偵測與自動錄影 + F3:時間軸與事件歷史)

對應規格書 `rule_doc/功能需求/07_spec_事件偵測與自動錄影.md`、
`rule_doc/功能需求/08_spec_時間軸與事件歷史.md`,部署形狀見
`rule_doc/功能需求/13_ADR_微服務與三節點部署.md`。擁有 `events` 表。

F2 與 F3 併在同一個服務,是因為兩者圍繞同一張表:F2 的偵測 worker 寫入、F3 的時間軸
API 讀取,拆開會變成兩個服務各自宣稱擁有 `events`(ADR 第 1 節)。

> **目前不連線任何真實資料庫。** ORM model 已依 `01_資料模型與儲存規格.md` 定義好,
> 需要 PostgreSQL 的測試標記為 `integration`,預設不執行。

## 快速開始

```bash
uv sync
uv run pytest                     # 235 個測試,不需要 PostgreSQL / R2 / 任何外部服務
uv run pytest -m integration      # 32 個,需 TEST_DATABASE_URL 或可用的 Docker
uv run pytest --cov=app           # 覆蓋率
uv run ruff check app tests
uv run mypy app
```

實際啟動(需先備妥 Postgres / R2 / Device / Push):

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8003   # F3 的時間軸 API
uv run python -m app.worker                              # F2 的偵測 worker(見「已知限制」)
```

## 程式結構

```
app/
├── main.py                    建 app、掛 router、lifespan
├── worker.py                  F2 偵測 worker 的進入點(不是 HTTP 服務)
├── core/                      config / database / orm / http 錯誤轉換 / security / system
├── shared_kernel/             錯誤分類、Clock 與 IdGenerator 介面(純 Python)
└── domains/
    ├── detection/             F2:錄影會話與事件寫入(07_spec)
    └── timeline/              F3:時間軸讀取、播放換發、已讀標記(08_spec)
```

每個領域內分四層,依賴只能由外向內:`presentation` / `infrastructure` → `application`
→ `domain`。`domain` 與 `application` 不 import FastAPI、SQLAlchemy、Pydantic,所以業務
規則不需要資料庫或 HTTP 就測得出來。分層規則由 `tools/check_layers.py` 機械化檢查,
並包成 `tests/architecture/test_layers.py`——違反時測試就紅燈。

**`events` 的 ORM 定義放在 `core/orm.py` 而不是某個領域裡**:兩個領域對應同一張表,
放進其中一個會逼另一個跨領域 import(違反分層規則第 4 條)。資料列是基礎設施細節,
兩個領域各自用自己的 mapper 轉成自己的型別——`detection` 轉 `Event` 聚合,
`timeline` 轉 `TimelineEvent` 唯讀視圖。

## API

| Method | Path | 說明 |
|---|---|---|
| GET | `/devices/{device_id}/events?cursor=&limit=&date=&tz=&from=&to=` | 事件列表(新到舊) |
| GET | `/events/{event_id}/playback-url` | 換發影片 presigned URL(10 分鐘) |
| PATCH | `/events/{event_id}` | 標記已讀(body 只接受 `is_read`) |
| DELETE | `/internal/devices/{device_id}/events` | **內部**:Device 移除裝置時串聯清除 |
| GET | `/health` | LB 健康檢查(不碰資料庫) |

錯誤回應一律 `{"error": {"code": "...", "message": "..."}}`,code 取自
`10_錯誤處理與狀態規範.md` 第 3 節與 08_spec 第 7 節。

**時間格式**:對外的時間欄位一律 **Unix timestamp**(秒,整數,UTC 基準);
儲存層維持 `timestamptz`(01_資料模型第 2.0 節),轉換只發生在 presentation 層。

### 路由邊界(規格審查 #1)

`/devices` 前綴屬於 **Device 服務**。七個服務掛同一個 Load Balancer,分流規則依
method + path 的形狀切分:`/devices/{id}/events` → Event,其餘 `/devices*` → Device。

### 跨服務呼叫

| 對象 | 端點 | 用途 |
|---|---|---|
| Device | `GET /internal/devices/{device_id}` | 驗證裝置擁有者(`events` 沒有 `user_id`) |
| Push | `POST /internal/notifications/event-ready` | 事件 `ready` 後觸發推播 |

都以 `X-Internal-Api-Key` 把關,只走 VCN 私有網路、不經 Load Balancer。

## 規格審查結論

開發前對 07/08 與相關規格做了一輪審查,八個阻斷問題經確認後的決議(已寫回 rule_doc):

1. **路由依 method + path 形狀分流**,見上。原本 `/devices/{id}/events` 會被 LB 導去
   Device 服務。
2. **新增 `DeviceOwnership` port**。三個端點原本都沒有擁有者驗證,而 `events` 沒有
   `user_id`、`devices` 表也不屬於本服務——任何登入者都能讀取與播放他人的寵物影片
   (IDOR)。**非本人與不存在一律回 404 `DEVICE_005`,不回 403**,避免洩漏存在性。
3. **列表回應直接夾帶縮圖的 presigned URL**。08_spec 沒有定義縮圖怎麼取得,但 R2 不是
   公開 bucket,不夾帶前端根本拿不到圖。
4. **新增 `TIMELINE_005`(409)**:對 `processing` 事件請求播放的行為原本未定義;
   `failed` 沿用 `EVENT_001`(改標 409)。
5. **保留期以 `started_at + 7 天`(縮圖 30 天)判定**,與 R2 lifecycle rule 同一個基準。
   資料庫不存 `expires_at`——那會多出第二個真相來源。
6. **`date` 篩選加 `tz`**(IANA,預設 `Asia/Taipei`),另支援 `from`/`to`(Unix timestamp)
   區間。資料以 UTC 儲存,不換算時區的話傍晚之後的事件會被歸到隔天。
7. **Push 端點改由 Event 主動呼叫**(`POST /internal/notifications/event-ready`)。
   通知標題需要的裝置名稱由 Push 自行向 Device 取即時值,Event 不夾帶。
8. **新增 `DELETE /internal/devices/{device_id}/events`**,且 **R2 物件由本服務刪除**。
   原契約要求呼叫端(Device)刪 R2,但它不知道 `event_id`,組不出 key。
9. **`events` 新增 `is_partial`**:斷線產生的不完整片段(`EVENT_003`)在原本的三態狀態機
   沒有落腳處,而 `failed` 的語意是「沒有可播放內容」,不能拿來表達「可播放但不完整」。

採用的假設(🟡 級,測試 docstring 內有標註):

| # | 假設 |
|---|---|
| A | 門檻值本身視為有活動(`score >= 0.6`)。§2.1 寫「超過門檻」、§2.2 寫「低於門檻」,門檻值本身兩邊都沒說到;寧可多錄一點,也不要讓剛好落在門檻上的影格提早結束錄影 |
| B | `limit` 預設 20、上限 100;超過回 `VAL_001` |
| C | `PATCH /events/{id}` 只接受 `is_read`,允許改回 `false`(誤點後標記未讀) |
| D | 事件不存在與非本人回同一個 404 `DEVICE_005`——前端的復原路徑相同(導回列表) |
| E | `confidence_score` 內部一律 `Decimal`;資料表是 `numeric(3,2)`,用 float 比較 0.6 門檻會有誤差 |
| F | 靜止結束的片段收在最後一次活動(不錄進後面那幾秒空景);60 秒上限則切在當下 |
| G | 達 60 秒上限而活動仍在繼續時,立刻開始下一個事件,不丟棄剩下的動作 |
| H | 資料層不可用時列表回 503 `SRV_002`,`TIMELINE_001`(500)留給其他非預期錯誤 |

## 測試

| 層 | 數量 | 說明 |
|---|---|---|
| domain | 79 | 業務規則窮盡:錄影合併與結束、狀態機、播放與保留期、游標與日期區間 |
| application | 59 | 編排:偵測迴圈、上傳重試、擁有者驗證、commit 與否、跨服務呼叫 |
| contract | 42 | 介面的行為承諾,fake 與 SQLAlchemy 跑同一份(後者 21 個標 `integration`) |
| presentation | 27 | HTTP 契約:狀態碼、錯誤碼、回應欄位、權限 |
| architecture | 26 | 分層依賴、每個實作明確繼承介面且無漏實作 |
| 對外契約 | 23 | `__init__.py` 與實作不得走樣 |
| infrastructure | 11 | mapping 往返精度、DB 約束(需真實 PostgreSQL) |

合計 267 個:預設執行 235,其餘 32 個需要真實 PostgreSQL。

覆蓋率 86%(domain 與 application 97~100%)。未覆蓋的部分集中在 infrastructure
(35~60%)——那些行都由標記 `integration` 的測試覆蓋,預設不執行。
`core/security.py`(60%)的 JWT 解碼路徑屬於 Auth 服務的職責範圍,本服務只驗證。

## 待辦:建立資料庫

等所有服務的規格都確認後再一次產出 DDL/migration。本服務已知需要的 schema 變更:

**`events` 新增 `is_partial boolean not null default false`**(規格審查 #9)。
已同步寫回 `rule_doc/功能需求/01_資料模型與儲存規格.md` 第 2.3 節、`db/models.py` 與
`db/migrations/versions/0001_initial_schema.py`(該 migration 尚未套用到任何真實資料庫,
所以直接改比再疊一個 migration 乾淨)。

## 已知限制

- **F2 的 RTSP 與 ffmpeg adapter 未實作**。錄影的業務規則(事件合併、5 秒靜止、
  60 秒上限、上傳重試 3 次、狀態收斂、斷線標記)已完整實作並測試,缺的是把影格與
  檔案接進來的那一層:實作 `FrameSource` 與 `ClipEncoder` 之後傳進
  `app/worker.py` 的 `build_worker` 就能跑。這台開發機沒有鏡頭也跑不了模型,
  硬寫只會得到測不了的程式碼。
- **事件何時寫入 `events` 表**:07_spec §3.1 寫「錄影結束,事件寫入」,但對外契約原本
  寫「觸發錄影當下建立」。目前照規格書:錄影結束後先寫入 `processing`,上傳完成才轉
  `ready`。差別是使用者在錄影當下(最多 60 秒)看不看得到「處理中」卡片。
  **這一點值得再確認**——若要錄影當下就可見,把 `Event.begin` 的寫入移到
  `DetectMotion._start`。
- **推播失敗不重試**:事件已經 `ready` 是事實,推播沒送出是另一回事。Push 服務收到
  請求就回 202,發送在它那邊背景進行。
- **多鏡頭的 worker 尚未做排程**:`run_forever` 只是 `asyncio.gather`,一支鏡頭斷線後
  不會自動重連,需要外層的重啟策略。
- **`GET /health` 不檢查資料庫**:這支回答的是「這個複本還活著嗎」。把資料層故障傳染
  到健康檢查,會讓 LB 同時拔掉兩台還能正常走降級路徑的節點。
