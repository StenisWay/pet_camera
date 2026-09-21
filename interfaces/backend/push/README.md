# Push 服務(F4:推播通知)

對應規格書 `rule_doc/功能需求/09_spec_推播通知.md`(第 8 節為規格審查決議,程式註解中的
「審查 #N」對應該表),部署形狀見 `rule_doc/功能需求/13_ADR_微服務與三節點部署.md`。

## 快速開始

```bash
uv sync
uv run pytest                      # 154 個測試,不需要任何外部服務
uv run pytest -m integration       # 16 個,需要 Docker 或 TEST_DATABASE_URL
uv run pytest --cov=app --cov-report=term-missing
uv run python tools/check_layers.py --root .   # 分層依賴檢查
uv run ruff check app tests
uv run mypy app
```

實際啟動(設定以 `PUSH_` 為前綴的環境變數,見 `app/core/config.py`):

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8004
```

## 架構

```
app/
├── main.py                      composition root:建 app、組 adapter、lifespan
├── orm_models.py                匯總 ORM model(給 Alembic 比對與整合測試)
├── shared_kernel/               純 Python:錯誤分類、Clock/IdGenerator 介面
├── core/                        config、database、http 錯誤轉換、security、限流
└── domains/
    ├── push_tokens/             端點登記(09_spec §2.4、§2.5);擁有 push_tokens 表
    │   └── api.py               對 notifications 公開的唯一入口
    └── notifications/           事件 ready 後的推播與防洗版(§2.1–2.3);不持有任何資料表
```

每個領域分 `domain / application / infrastructure / presentation` 四層,依賴只能由外向內,
`tools/check_layers.py` 機械化檢查並被 `tests/architecture/` 當成測試跑。

- **業務規則在 domain**:換帳號改綁(`PushToken.rebind_to`)、計數窗位置
  (`Occurrence.from_window_count`)、通知文案與 deep link 目標(`ReadyEvent.notification_for`)、
  哪些縮圖可以簽(`ReadyEvent.signable_thumbnail_key`)。
- **notifications 的所有外部依賴都是 port**:Device 服務、Redis 計數窗、R2、推播管道、
  收件端點(經 `push_tokens.api`)。
- **介面一律 ABC**,每個介面都有正式實作與 fake;`tests/domains/*/contracts/` 讓同一份合約測試
  跑在 fake 與 SQLAlchemy 上。

## 端點

| Method | Path | 呼叫者 | 回應 |
|---|---|---|---|
| PUT | `/push-tokens` | App/Web | 200 `{id, platform, created_at}`(不含 token);每使用者每分鐘 10 次 |
| GET | `/push-tokens` | App/Web | 200 `{items: [{id, platform, created_at}]}` |
| DELETE | `/push-tokens/{push_token_id}` | App/Web | 204;非本人與不存在一律 404 |
| POST | `/internal/notifications/event-ready` | Event worker | 202,背景發送;`X-Internal-Api-Key` 把關 |
| GET | `/health` | Load Balancer | 不碰資料庫 |

## 降級行為(13_ADR 第 4 節)

| 故障 | 行為 |
|---|---|
| Postgres 連不到(登記/解除) | 503 `SRV_002`(寫入選 C) |
| Postgres / Device 服務連不到(發送) | 延後重試 `PUSH_LOOKUP_RETRY_DELAYS_SECONDS`(預設 1、3、5 秒),用盡寫 ERROR 後放棄 |
| Redis 計數窗連不到 | 視為首發,照常推播(寧可多推,不可漏推) |
| Redis 限流連不到 | fail-open |
| R2 簽不出縮圖 | 通知不附圖,照常送出 |
| 推播服務回報端點失效 | 刪除該筆(`PUSH_003`),不影響其他端點 |
| 推播服務其他錯誤(逾時、配額、5xx) | 不刪端點 |

## 設計假設(規格未明寫,需前端/其他服務確認)

1. **App 端一律走 FCM**(Android 與 iOS 都向 FCM 取 token,由 FCM 轉送 APNs)。
   `platform` 值域只有 `app`/`web`,後端無從分辨 iOS 原生 APNs token,所以不直接呼叫 APNs。
   `apns_*` 設定目前沒有使用。
2. **Deep link 格式**:App `petcamera://devices/{device_id}?event_id={event_id}`,
   Web `{web_base_url}/dashboard/devices/{device_id}?event_id={event_id}`;合併通知不帶 `event_id`。
   依 screens/*/02、04,通知導向攝影機畫面,由畫面依 `event_id` 播放該事件。
3. **通知內文**照 §2.2 字面為「高信心」/「一般」。
4. **`thumbnail_object_key` 必須在 `thumbnails/{device_id}/` 底下**才會簽 URL,
   否則通知不附圖——避免被攻破的呼叫端讓本服務替任意 R2 物件簽出連結。
5. 推播 TTL 1 小時:超過一小時才送達的「寵物有動靜」沒有意義。

## 已知限制

- 真正打到 FCM / Web Push 需要憑證(`PUSH_FCM_PROJECT_ID`、`PUSH_FCM_CREDENTIALS_JSON`、
  `PUSH_WEB_PUSH_VAPID_PRIVATE_KEY`)。未設定時該管道一律回 FAILED 並寫 WARNING,
  **不會**把端點當成失效刪掉。三種管道的實機送達(驗收 §7)需要憑證備妥後手動驗證。
- 背景發送用 FastAPI `BackgroundTasks`:複本在發送中途被重啟,該則通知會遺失。規格選擇
  「推播晚到或偶爾漏掉」優於增加佇列元件(13_ADR 第 5 節);若日後要保證送達,需改成持久化佇列。
- ORM 不宣告對 `users.id` 的外鍵(users 屬於 Auth);`ON DELETE CASCADE` 由共用的
  `db/migrations/` 建立,刪除帳號時 push_tokens 一併刪除,本服務不需要端點。
