# Device 服務(F0.2:裝置配對 + F0.3:裝置管理)

對應規格書 `rule_doc/功能需求/03_spec_裝置配對.md`、`04_spec_裝置管理.md`,
部署形狀見 `rule_doc/功能需求/13_ADR_微服務與三節點部署.md`。擁有 `devices` 表。

> 這裡的「裝置」是**攝影機硬體**,與 Push 服務的用戶端 token 是不同概念
> (`01_資料模型與儲存規格.md` 第 2.6 節)。

> **目前不連線任何真實資料庫。** ORM model 已依 `01_資料模型與儲存規格.md` 定義好,
> 建表/migration 等規格全部確認後再一次產出,見下方「待辦:建立資料庫」。
> 預設的 140 個測試不需要 PostgreSQL / Redis 任何一項。

## 快速開始

```bash
uv sync
uv run pytest                     # 140 個測試(不需要資料庫)
uv run pytest -m integration      # 另外 24 個,需要 PostgreSQL
uv run pytest --cov=app
uv run ruff check app tests
uv run mypy app
uv run python tools/check_layers.py --root .
```

實際啟動(需要先備妥 Postgres、Event 服務):

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
```

## 程式結構

```
app/
├── main.py                      建 app、掛 router、lifespan、/health
├── core/                        config / database / http_errors / security / rate_limit / system
├── orm_models.py                Alembic 與測試的 metadata 匯入點
└── domains/devices/
    ├── domain/                  Device 實體、PairingCode 值物件、例外、DeviceRepository(ABC)
    ├── application/             七個 use case、DTO、ports(ABC)
    ├── infrastructure/          ORM、mapper、repository、UnitOfWork、Event 服務 adapter
    └── presentation/            router、internal_router、schemas、組裝點
```

依賴方向只能由外向內,由 `tools/check_layers.py` 機械化檢查,並包成
`tests/architecture/test_layers.py`。`tests/architecture/test_interfaces.py` 另外確認
每個實作都**明確繼承**介面且沒有漏實作抽象方法。

單一領域 `devices`,沒有拆成 `pairing` + `device_management`:兩者操作的是同一個
`Device` 聚合、同一台狀態機、同一張表,拆開會變成兩個領域共用一個 repository。

## API

| Method | Path | 呼叫者 | 說明 |
|---|---|---|---|
| POST | `/devices/register` | 鏡頭(匿名) | 取得配對碼與 device secret,以 `hardware_id` 冪等 |
| POST | `/devices/pair` | 使用者 | 輸入配對碼完成綁定 |
| POST | `/devices/{id}/heartbeat` | 鏡頭(`X-Device-Secret`) | 心跳,每 30 秒 |
| GET | `/devices` | 使用者 | 已配對裝置列表,含線上/離線 |
| PATCH | `/devices/{id}` | 使用者 | 重新命名 |
| DELETE | `/devices/{id}` | 使用者 | 移除裝置(連同事件與影片) |
| GET | `/internal/devices/{id}` | **內部** Event / Push | `DeviceSummary`,見服務契約 `__init__.py` |
| DELETE | `/internal/users/{user_id}/devices` | **內部** Auth | 刪除帳號時串聯移除 |
| GET | `/health` | LB | 健康檢查(不碰資料庫) |

錯誤回應一律 `{"error": {"code": "...", "message": "..."}}`,code 取自
`10_錯誤處理與狀態規範.md` 第 3 節與 03/04_spec 第 5 節。內部端點以
`X-Internal-Api-Key` 把關,只走 VCN 私有網路。

## 規格審查結論

開發前對 03/04_spec 做了一輪審查,九個阻斷問題經確認後的決議:

1. **擁有者驗證,非本人一律回 404 `DEVICE_005`**(不回 403)。規格書原本完全沒提
   `PATCH` / `DELETE` 的擁有者驗證,等於任何登入者帶別人的 `device_id` 就能改名、
   或移除他人鏡頭並刪光對方所有事件影片(IDOR)。回 403 會洩漏資源存在性。
2. **新增鏡頭端憑證** `devices.device_secret_hash`。原本 `/devices/register` 與
   `/heartbeat` 沒有任何身分驗證,知道 `device_id` 就能偽造心跳,讓實際已斷線的鏡頭
   永遠顯示「在線」。secret 只在建立該列時簽發一次,回應裡出現一次,只存雜湊。
3. **新增 `devices.hardware_id`(unique)讓 register 冪等**。規格沒處理「已配對的鏡頭
   重開機也會開機」,照原樣每次開機都會多長一筆孤兒列。三種情況見
   `application/use_cases/register_device.py` 的說明。
4. **配對碼採 8 碼 Crockford Base32**(排除 I/L/O/U),大小寫不敏感、容許連字號、
   I·L→1、O→0。32^8 ≈ 1.1 兆組是主要防線。
5. **刪除 `DEVICE_003`**,已配對的碼一律回 `DEVICE_002`。原規格在 §2.2 要求配對成功後
   清除 `pairing_code`,那麼「已被配對的裝置的配對碼」在 DB 裡根本查不到,
   `DEVICE_003` 永遠不可能觸發——但驗收標準第 4 條還要求它。
6. **`offline` 改為衍生狀態**,`status` 欄位只存 `pending` / `paired`。原規格要落盤的話
   需要背景掃描任務,但本服務在 VM-1/VM-2 各跑一份複本,兩份都掃會打架,而系統沒有
   可用的單例排程器。改成由 `last_seen_at` 推導後不需要背景任務,且 Stream 服務
   (`06_spec` STREAM_001)與本服務用同一條規則,不會對同一台鏡頭有不同看法。
7. **新增 Event 服務的內部端點 `DELETE /internal/devices/{device_id}/events`**。
   `04_spec` §2.3 要求移除裝置時刪掉事件與 R2 物件,但 `events` 表屬於 Event 服務,
   而全 rule_doc 裡不存在任何可呼叫的端點。注意 `events.device_id` 雖是 CASCADE,
   但 unpair **不刪** `devices` 這一列,cascade 不會觸發,必須顯式呼叫。
8. **新增本服務的內部端點 `DELETE /internal/users/{user_id}/devices`**。
   `01_資料模型` §2.2 的 `ON DELETE SET NULL` 與同節 CHECK「`status='pending'` 與
   `user_id is null` 必須同時成立」互相矛盾——直接刪 `users` 會讓該帳號名下
   `paired` 裝置的 `user_id` 被設為 null,當場違反 CHECK,**刪除帳號那句 SQL 會失敗**。
   Auth 必須在刪 `users` 之前先呼叫這個端點。
9. **移除裝置 fail-closed**:固定「先請 Event 清事件 → 成功後才 unpair」,Event 回非 2xx
   就整個 `DELETE` 失敗回 `SRV_002`,裝置維持原狀。反過來做的話,刪事件失敗會留下
   「事件還在、裝置已回 pending」,下一位配對者就會看到前一位使用者的寵物影片。

採用的假設(🟡 級,測試 docstring 內有標註):

| # | 假設 |
|---|---|
| 10 | 同一組配對碼的併發配對以 `SELECT ... FOR UPDATE` 序列化,第二個請求得到 `DEVICE_002` |
| 11 | `name` trim 後 1~30 字、可重名;register 時預設 `未命名鏡頭`(命名畫面在配對**之後**) |
| 12 | `PATCH` 只收 `name`,`extra="forbid"` 擋 mass assignment,多帶欄位回 `VAL_001` |
| 13 | `GET /devices` 不分頁、固定 `ORDER BY created_at, id`;每帳號配對上限 20 台 |
| 14 | `pending` 裝置送心跳回 409;配對碼過期後由鏡頭重新呼叫 register 取碼 |
| 15 | register 回應含 `pairing_code_expires_at`,鏡頭才知道何時該重取 |
| 16 | `DEVICE_004`(心跳逾時)是 UI 狀態不是錯誤回應,不對應任何端點 |

### 對審查 #4 的一處修正

審查報告原寫「同一配對碼連續錯 5 次即作廢該碼」。實作時確認那**擋不住暴力破解**:
攻擊者亂猜的碼不會對應到任何裝置,沒有任何計數器會被遞增。真正有效的是
(a) 1.1 兆組的碼空間與 (b) 對**呼叫端**限流。因此改成 `/devices/pair` 單獨設
10 次/分(沿用 `10_錯誤處理` §3 既有的 RATE_001 機制與 Redis 用途,不動 ADR §1.1),
**不在 `devices` 加 `failed_pair_attempts` 欄位**。

## 待辦:建立資料庫

等規格全部確認後再一次產出 DDL/migration。目前已知需要的 schema 變更(`devices` 表):

| 欄位 | 變更 | 來源 |
|---|---|---|
| `hardware_id` | **新增** text, not null, unique | 審查 #3 |
| `device_secret_hash` | **新增** text, not null | 審查 #2 |
| `status` | 值域由 `pending`/`paired`/`offline` 縮小為 **`pending`/`paired`** | 審查 #6 |
| `name` | 補 not null 與 `CHECK char_length BETWEEN 1 AND 30` | 審查 #11 |

另需補上三條 CHECK(已寫在 `infrastructure/orm.py`):
`(status='pending') = (user_id IS NULL)`、`(pairing_code IS NULL) = (pairing_code_expires_at IS NULL)`、
`status='pending' OR pairing_code IS NULL`。

外鍵 `user_id -> users.id ON DELETE SET NULL` 由 `db/` 的共用 migration 建立,不在本服務的
ORM 宣告——`users` 表屬於 Auth 服務,寫了會讓測試的 `create_all` 解不到目標表。

## 已知限制

- **Event 服務的 `DELETE /internal/devices/{id}/events` 尚未實作**。本服務這一側的 port、
  adapter、fail-closed 流程與測試都已完成;對方實作完成前,`DELETE /devices/{id}` 在真實
  環境會得到 `SRV_002` —— 這正是 fail-closed 期望的行為,不會留下殘留的事件。
- **24 個 integration 測試尚未在本機執行過**(開發機沒有可用的 PostgreSQL)。
  它們涵蓋 mapping 往返、timestamptz、四條 CHECK、兩個唯一索引與 `FOR UPDATE` 的併發序列化。
  有 Docker 或 `TEST_DATABASE_URL` 時以 `uv run pytest -m integration` 執行。
- **限流尚未接上 Redis**:`core/rate_limit.py` 的 `RateLimitCounter` 還沒有正式實作,
  `pair` / `register` 的限流設定已在 `config.py`,但尚未掛進 router。
- **鏡頭遺失 device secret 需要回復原廠設定**。register 只在建立新列時簽發 secret,
  已存在的裝置不重發——`hardware_id` 不是秘密,重發等於讓任何知道它的人接管鏡頭身分。
- **App token 滑動展延未實作**(`02_spec` §2.3.2)。那需要各服務都能簽發 token,
  屬於 Auth 服務的職責,本服務只驗證。這是跨服務的設計缺口,需要另外決定由誰負責
  (Album 服務的 README 也記了同一條)。
- 服務對外契約 `__init__.py` 裡的 `DeviceRepository` Protocol 是**資料表導向的 CRUD**
  (`create_pending` / `pair` / `rename` / `update_status`),與本服務實際採用的聚合式
  repository 不同。實際實作見 `domain/repositories.py`;契約那份需要更新,
  但該檔案同時有其他服務在編輯,留待合併時一併處理。
