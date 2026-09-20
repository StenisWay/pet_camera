# Album 服務(F6:相簿與 Google Drive 匯出)

對應規格書 `rule_doc/功能需求/12_spec_相簿與雲端匯出.md`,部署形狀見
`rule_doc/功能需求/13_ADR_微服務與三節點部署.md`。

> **目前不連線任何真實資料庫。** ORM model 已依 `01_資料模型與儲存規格.md` 定義好,
> 需要真實 PostgreSQL 的測試標記為 `integration` 並**預設不執行**;建表與 Alembic
> migration 等所有服務的規格確認後再一次產出,見下方「待辦:建立資料庫」。

## 快速開始

```bash
uv sync
uv run pytest                      # 180 個測試,不需要任何外部服務
uv run pytest -m integration       # 需要 Docker 或 TEST_DATABASE_URL
uv run pytest --cov=app --cov-report=term-missing
uv run python tools/check_layers.py --root .   # 分層依賴檢查
uv run ruff check app tests
uv run mypy app
```

實際啟動(需先備妥 Postgres / Redis / R2 / Google 憑證):

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8006
```

## 架構

第一層按業務領域切,第二層才是技術分層(Clean Architecture)。改「匯出規則」時,
動到的檔案集中在 `domains/drive_export/`。

```
app/
├── main.py                      composition root:建 app、組 adapter、lifespan
├── orm_models.py                匯總所有 ORM model(給 Alembic 與測試)
├── shared_kernel/               純 Python:錯誤分類、Clock/IdGenerator 介面、分頁游標
├── core/                        框架相關:config、database、http 錯誤轉換、security、限流
└── domains/
    ├── album/                   相簿瀏覽與刪除(12_spec §2.1、§2.2)
    │   ├── domain/              實體(業務規則所在地)、值物件、repository 介面
    │   ├── application/         use case、DTO、port(UnitOfWork、讀取端、物件儲存)
    │   ├── infrastructure/      ORM、mapper、repository 實作、R2 adapter
    │   ├── presentation/        FastAPI router、Pydantic schema、組裝點
    │   └── api.py               對其他領域公開的唯一入口
    └── drive_export/            Google Drive 授權與匯出(12_spec §2.3),同樣四層
tests/                           鏡像 app 結構,外加 architecture/、e2e/
tools/check_layers.py            分層依賴檢查(也被 tests/architecture 當測試跑)
```

依賴方向只能由外向內:`presentation`/`infrastructure` → `application` → `domain` →
`shared_kernel`。具體效果:

- **業務規則在實體裡**。匯出狀態機是 `AlbumItem.start_export()` / `complete_export()` /
  `fail_export()` / `is_export_stale()`,不是 use case 裡的 if/else。
- **實體不是 ORM model**。`AlbumItem` 是純 dataclass,`MediaItemRow` 是資料列,中間
  用 mapper。資料表可以依 `01_資料模型與儲存規格.md` 自由演進而不牽動業務規則。
- **domain / application 不 import 框架**,所以 149 個測試裡有一大半根本不需要
  FastAPI、SQLAlchemy 或任何網路。
- **跨領域只能走對方的 `api.py`,而且只能在 infrastructure**。`drive_export` 在
  application 定義 `AlbumContent` port,在 infrastructure 寫 adapter 接到 `album.api`,
  composition root 負責接線——兩個領域的內層互不知道對方存在。

這些規則不是靠自律,`tools/check_layers.py` 會機械化檢查,並且被
`tests/architecture/test_layers.py` 當成測試跑,違反時直接紅燈。

### 介面與合約測試

介面一律 `ABC` + `@abstractmethod`,實作**明確繼承**——漏實作任何方法時建立實例
當下就 `TypeError`,不必等執行到那一行。每個介面都有兩個實作(正式 + fake),
`tests/architecture/test_interfaces.py` 逐一檢查它們可被實例化,
`tests/domains/*/contracts/` 則讓**同一份測試跑在兩個實作上**——fake 的行為與正式
實作一致,application 層用 fake 得到的綠燈才可信。

## API

| Method | Path | 說明 |
|---|---|---|
| GET | `/media?date=&from=&to=&cursor=&limit=` | 相簿項目分頁(新到舊) |
| DELETE | `/media/{media_item_id}` | 刪除項目(連同 R2 物件) |
| GET | `/integrations/google-drive/oauth-url` | 取得 Google 授權連結 |
| POST | `/integrations/google-drive/oauth-callback` | 完成授權綁定 |
| POST | `/media/export/google-drive` | 送出匯出請求(202 受理) |
| DELETE | `/internal/users/{user_id}/media` | **內部**:Auth 刪除帳號時串聯清除 |
| GET | `/health` | LB 健康檢查(不碰資料庫) |

錯誤回應一律 `{"error": {"code": "...", "message": "..."}}`。領域例外只宣告自己的
業務分類與錯誤碼,狀態碼對應集中在 `core/http_errors.py`,依
`10_錯誤處理與狀態規範.md` 第 3 節:`NotFound`→404、`Conflict`→409、
`PermissionDenied`→403、`BusinessRuleViolation`→400(`VAL_001`)、
`AuthenticationRequired`→401(`AUTH_001/002`、`DRIVE_001/003`)、`RateLimited`→429、
`ServiceUnavailable`→503。

`GET /media` 的日期分組與篩選用**台北時間**(`12_spec §2.1`),資料仍以 UTC 儲存;
時區是設定值 `ALBUM_TIMEZONE`,未來要支援跨時區時改這一處。

### 路由邊界(規格審查 #3)

`GET /media/{id}`(單筆內容查詢)屬於 **Media 服務**,本服務不提供。
Load Balancer 分流:`GET /media`、`DELETE /media/{id}`、`POST /media/export/google-drive`
→ Album;`GET /media/{id}` → Media。

## 規格審查結論

開發前對規格做了一輪審查,四個阻斷問題經確認後的決議:

1. **列表回傳三種 status**(`processing` / `ready` / `failed`)。12_spec §2.1 原寫
   「僅列出 ready」,與 11_spec §4 要求的「相簿卡片顯示處理中 spinner / 失敗錯誤圖示」
   衝突;§2.1 改解讀為「只有 ready 可播放/匯出」。
2. **新增 `google_drive_credentials` 表**存 Drive 的 refresh token。不與 Auth 服務的
   `oauth_identities` 混用——那是登入身分綁定,這是 `drive.file` 授權。
3. **路由依 method + path 形狀分流**,見上。
4. **repository 介面補 `get` / `get_many`**。原介面無法在刪除/匯出前驗證擁有者,
   等於任何登入者可刪除他人相簿項目(IDOR)。非本人一律回 404 而非 403,
   避免洩漏資源存在性。

採用的假設(🟡 級,測試 docstring 內有標註):

| # | 假設 |
|---|---|
| 5 | `date=YYYY-MM-DD`(App 單日)與 `from`/`to`(Web 區間)互斥,格式嚴格,空字串視為未指定 |
| 13 | **相簿依日期分組/篩選用台北時間**(`ALBUM_TIMEZONE`,預設 `Asia/Taipei`);`captured_at` 仍以 UTC 儲存,只在判斷「屬於哪一天」時換算 |
| 6 | 單次匯出上限 50 筆;已 `exporting` 的項目跳過不重送 |
| 7 | `exporting` 超過 15 分鐘改判 `failed`,由 lifespan 內的掃描任務執行 |
| 8 | OAuth `state` 存 Redis(TTL 10 分)防 CSRF;**Redis 不可用時 fail-closed 回 `SRV_002`**(限流才 fail-open) |
| 9 | 新增 `DELETE /internal/users/{user_id}/media`,以 `X-Internal-Api-Key` 把關 |
| 10 | `exporting` 中仍可刪除;只有 `ready` 可匯出,其餘 `VAL_001` |
| 12 | **列表回應直接夾帶 10 分鐘效期的 presigned URL**。12_spec 沒有定義相簿縮圖如何取得,但網格一次顯示 30 張,逐一去 Media 服務換 URL 不合理 |

## 待辦:建立資料庫

等規格全部確認後,依 `postgres-db-master` 產出並審查 Alembic migration。目前已知:

1. **新表 `google_drive_credentials`**(Album 服務擁有):`id` PK、`user_id` unique
   FK→users ON DELETE CASCADE、`refresh_token`(**需加密**)、`drive_folder_id`、
   `connected_at`、`created_at`、`updated_at`。
2. **`media_items` 不需要新增欄位**。匯出逾時判定用第 2.0 節既有的 `updated_at`
   (由 trigger 維護)——處於 `exporting` 的項目不會再被 Media 服務寫入。
3. `media_items` 的索引由 `(user_id, captured_at desc)` 改為
   `(user_id, captured_at desc, id)`,組合游標分頁需要。

以上 1、3 已寫回 `rule_doc/功能需求/01_資料模型與儲存規格.md`(第 2.4、2.8、6 節),
規格審查的決議也寫回 `12_spec_相簿與雲端匯出.md`(第 2.1、2.3、3 節)。

## 已知限制

- **不做 token 滑動展延,這是規格內的正解**:`02_spec §2.3.2` 已明定展延由 Auth 服務的
  `POST /auth/token/extend` 專責,七個服務只用共用密鑰驗證。Album 因此不持有簽發能力。
- `refresh_token` 目前以明碼欄位存放,建表時需確認加密方式(KMS / pgcrypto / 應用層)。
- 匯出走 FastAPI background task,服務複本重啟會遺失進行中的任務——由假設 #7 的逾時
  掃描收斂成 `failed`,使用者重試即可。量體變大時改用獨立 worker。
- 匯出時整個檔案讀進記憶體再上傳(剪輯上限 5 分鐘,見 `11_spec §2.2`)。
  單檔變大時需改成 resumable upload 串流。
- infrastructure 層(SQLAlchemy 實作、R2、Google HTTP、Redis)的測試都在
  `-m integration` 裡,目前未執行,所以整體覆蓋率停在 84%;domain 與 application
  兩層是 100%。
