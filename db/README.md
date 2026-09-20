# 資料庫(PostgreSQL)

七個微服務共用的單一 PostgreSQL 資料庫。schema 的唯一事實來源是
[`rule_doc/功能需求/01_資料模型與儲存規格.md`](../rule_doc/功能需求/01_資料模型與儲存規格.md),
本資料夾是它的可執行版本。

| 檔案 | 用途 |
|---|---|
| `models.py` | SQLAlchemy 2.0 model,Alembic autogenerate 的比對基準 |
| `migrations/versions/` | Alembic migration,正式環境唯一的 schema 變更途徑 |
| `scripts/bootstrap_local.sh` | 建立本地資料庫與三個最小權限帳號 |
| `schema.sql` | 由已套用的資料庫匯出的 DDL,純供審閱,**不要拿它建庫** |
| `.env.example` | 連線字串範本;實際的 `.env` 不進版控 |

## 本地安裝(Ubuntu)

```bash
# 1. 安裝 PostgreSQL 16
sudo apt-get update && sudo apt-get install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql

# 2. 建立資料庫與帳號
sudo db/scripts/bootstrap_local.sh

# 3. 安裝 Python 相依
cd db && uv venv --python 3.12
uv pip install "sqlalchemy>=2.0.36" "alembic>=1.14.0" "psycopg[binary]>=3.2.3"

# 4. 建 schema
cp .env.example .env
set -a; . ./.env; set +a
uv run alembic upgrade head
```

驗證:

```bash
psql pet_camera -c '\dt'          # 應有 7 張表 + alembic_version
uv run alembic current            # 應顯示 0001 (head)
```

## 帳號與權限

| 帳號 | 權限 | 給誰用 |
|---|---|---|
| `pet_camera_migrate` | 改 schema(CREATE/ALTER/DROP) | 只給 Alembic |
| `pet_camera_app` | SELECT / INSERT / UPDATE / DELETE | 七個微服務 |
| `pet_camera_readonly` | SELECT | 分析、報表、手動查詢 |

`ALTER DEFAULT PRIVILEGES` 已設定,日後 migration 新建的表會自動帶上 app / readonly
的權限,不需要每次手動 `GRANT`。

服務連線一律用 `pet_camera_app`;**不要**讓服務拿 migrate 帳號跑。

## 日常操作

```bash
set -a; . ./.env; set +a

uv run alembic revision --autogenerate -m "add xxx"   # 產生後務必逐行人工檢查
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic history --verbose

# 重新匯出審閱用 DDL
pg_dump --schema-only --no-owner --no-privileges pet_camera > schema.sql
```

**autogenerate 的產出一定要人工逐行檢查**:它會把「欄位改名」判斷成 drop + add,
直接套用會遺失該欄位所有資料。欄位改名要走 expand–contract(新增欄位 → 雙寫 →
回填 → 切讀取 → 移除舊欄位),分多次部署。

## 設計決策

規格書沒寫明、但建表時必須決定的事項,以及選擇的理由:

| # | 決策 | 理由 |
|---|---|---|
| 1 | 每張表加 `updated_at`,由 `set_updated_at()` trigger 維護 | 規格只列了 `created_at`,但 `devices.status`、`events.status`、`media_items.drive_export_status` 都會被更新,沒有 `updated_at` 就無法排查「這筆什麼時候被改的」。用 trigger 而非應用程式寫入,是因為有七個服務會寫同一個庫,漏寫只是時間問題 |
| 2 | 主鍵 `uuid` 預設 `gen_random_uuid()`,但應用程式應產生 **UUIDv7** | id 會出現在 R2 object key 與 API 路徑上,需由用戶端/服務端分散產生。UUIDv7 有時間排序,對 B-tree 索引友善,插入不會像 UUIDv4 那樣打散索引頁。DB 的預設值只是直接用 psql 塞測試資料時的保險 |
| 3 | `events` / `media_items` 的 object key、`duration_sec` 可為 NULL | 規格的狀態機說 `processing` 時「尚無可播放影片」,代表建立當下還沒有 key。改用 CHECK 表達真正的規則:`status = 'ready'` 時這些欄位必須存在 |
| 4 | `users.email` 強制小寫儲存(CHECK + UNIQUE) | 規格只說 unique。若不正規化,`A@x.com` 與 `a@x.com` 會是兩個帳號,使用者會登不進自己的帳號。選擇在 DB 層強制而非用 `citext`,是因為規則明確可見、不需額外擴充套件 |
| 5 | `devices`:`(status = 'pending') = (user_id is null)` | 由 03_spec 推出:register 產生 pending 且無擁有者,pair 後轉 paired 並綁定 `user_id`,unpair 重置回 pending 並清空 `user_id`。`offline` 是已配對裝置失聯,仍有擁有者 |
| 6 | `devices.pairing_code` 用部分唯一索引(`where pairing_code is not null`) | 配對碼在有效期間必須唯一,否則兩台裝置可能被同一組碼綁走;配對完成後清為 NULL,這些 NULL 不該互相衝突 |
| 7 | `media_items.source_event_id` 為 `ON DELETE SET NULL` | 解除配對會刪掉該裝置所有 `events`,但規格明訂相簿內容是使用者資產、不受影響。若用 CASCADE,使用者手動保存的剪輯會跟著事件一起消失——這是不可逆的資料遺失 |
| 8 | `media_items.device_id` 為 `ON DELETE RESTRICT` | 規格中裝置列不會被刪除(只重置為 pending)。RESTRICT 讓「有人真的去刪 devices 列」這件事直接失敗,而不是安靜地帶走相簿資料 |
| 9 | `devices.user_id` 為 `ON DELETE SET NULL` | 規格第 6 節:刪帳號時裝置回到 pending、`user_id` 清空,裝置本身可重新配對給別人 |
| 10 | `push_tokens` 唯一索引用 `(platform, md5(token))` | 同一個推播端點重複登記會讓使用者同一則通知收兩遍。用 md5 是因為 Web Push subscription 是 JSON 字串,直接建 B-tree 索引有 2704 bytes 上限風險 |
| 11 | `oauth_identities` 加 `UNIQUE (user_id, provider)` | 規格只要求 `(provider, provider_user_id)` 唯一。再加這條是避免同一使用者把兩個 Google 帳號綁到同一個 `users`,登入時無法判斷該用哪一筆 |
| 12 | 狀態欄位用 `text` + CHECK,不用 PG enum | 之後要新增狀態值(例如 `event_type` 加入 `sound`)只要改 CHECK,不必動型別定義;PG enum 的值域變更在有依賴時會很麻煩 |
| 13 | 只建一個資料庫、不做 database-per-service | 沿用 `13_ADR_微服務與三節點部署.md` 第 5 節的決策。表的擁有權靠服務邊界約束,不靠實體隔離 |

## 尚未處理(進正式環境前要補)

- 備份與 PITR:本地開發沒設定。正式環境要有自動備份 + 定期演練還原——沒測過還原的備份等於沒有備份
- `pg_stat_statements`:正式環境要開,否則出事時查不出是哪支查詢慢
- Redis(01 規格第 7 節)尚未安裝,本地要跑 Stream / Push / 限流相關功能時再補
