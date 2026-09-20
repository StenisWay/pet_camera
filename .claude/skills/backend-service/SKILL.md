---
name: backend-service
description: 實作或修改 interfaces/backend/<service>/ 底下的後端微服務(auth / device / event / stream / push / media / album)。涵蓋規格審查閘門、領域切分 + Clean Architecture 四層、TDD 循環,以及本專案特有的規範——對外契約 __init__.py、rule_doc 錯誤碼、ADR 的服務與資料表邊界、CAP 降級規則、暫不連真實資料庫。使用者說「把 X 服務做出來」「依 __init__.py 的介面實作」「幫 X 服務加一個端點」「這個服務的測試」,或要動到 interfaces/backend/ 下任何 Python 程式碼時使用。純粹寫規格書用 rule-doc-writer,畫圖用 drawio-flowchart / uml-diagram,資料表與 migration 用 postgres-db-master。
---

# 後端微服務實作

本專案後端拆成七個服務,部署在三台 VM(見 `rule_doc/功能需求/13_ADR_微服務與三節點部署.md`)。
每個服務一個資料夾:`interfaces/backend/<service>/`。

搭配 `fastapi-master` skill 使用:那份定義通用的四層架構與 TDD 流程,這份補上本專案
特有的規範。衝突時以本專案的規格書為準,並把理由寫下來。

## 不可跳過的順序

```
規格審查(閘門) → 領域切分與分層設計 → TDD(由內而外) → 收尾驗證
```

寫任何程式碼(含測試)之前先讀完規格。規格錯誤是最貴的 bug。

## Phase 0:規格審查

要讀的檔案(缺一不可):

| 檔案 | 為什麼非讀不可 |
|---|---|
| `rule_doc/功能需求/0X_spec_<對應功能>.md` | 功能行為、API、錯誤碼、驗收標準 |
| `rule_doc/功能需求/01_資料模型與儲存規格.md` | 資料表、共同欄位慣例、R2 key、狀態機、串聯清除 |
| `rule_doc/功能需求/10_錯誤處理與狀態規範.md` | 全域錯誤碼與 UI 狀態模型 |
| `rule_doc/功能需求/13_ADR_微服務與三節點部署.md` | 服務/資料表歸屬、CAP 降級、刻意不做的事 |
| `rule_doc/功能需求/screens/{app,web}/0X_page_*.md` | 畫面實際需要的欄位與篩選條件 |
| `interfaces/backend/<service>/__init__.py` | 該服務的對外契約 |
| 相關服務的 `__init__.py` | 跨服務呼叫的形狀 |

這個專案已經踩過、每次都要再追一遍的問題:

1. **兩份功能規格書描述同一張表**(例 `media_items` 被 11_spec 與 12_spec 各講一次),
   對狀態過濾的說法可能相反。
2. **兩個服務搶同一個路徑前綴**:七個服務掛在同一個 LB 後面,`/media` 這種路徑要先
   確定誰收。
3. **規格要求保存的東西在資料模型裡沒有落腳處**(例如第三方授權憑證)。
4. **`__init__.py` 的 repository 缺 `get`**:沒有它就無法在刪除/更新前驗證擁有者,
   等於契約層級的 IDOR。
5. **只寫成功路徑**:背景工作沒有失敗收斂與逾時,狀態機就沒有終止保證。
6. **畫面規格需要的參數 API 沒有**(例:Web 有日期區間篩選,API 只有單日)。
7. **時區沒講清楚**:「依日期分組」「今天」用哪個時區,資料模型只說「以 UTC 儲存」。

輸出規格審查報告,🔴 有阻斷問題時停下來等使用者回覆(每題附建議答案,讓他可以直接
回「照建議」)。審查結論確定後,把決議**寫回 rule_doc**,不要只留在程式碼註解裡。

規格書是活的:實作期間使用者可能同時在改它。動 rule_doc 之前先重讀目前內容,
只做加法,不要蓋掉別人的編輯。

## Phase 1:領域切分與四層

服務內部先依業務領域切,每個領域內再分四層:

```
app/
├── main.py                 composition root:建 app、組 adapter、lifespan
├── orm_models.py           匯總所有 ORM model
├── shared_kernel/          純 Python:錯誤分類、Clock/IdGenerator、共用值物件
├── core/                   框架相關:config、database、http_errors、security、限流
└── domains/<領域>/
    ├── domain/             實體(業務規則)、值物件、領域例外、repository 介面
    ├── application/        use case、DTO、port(UnitOfWork、外部服務、其他領域)
    ├── infrastructure/     ORM、mapper、repository 實作、外部 adapter
    ├── presentation/       router、Pydantic schema、組裝點
    └── api.py              對其他領域公開的唯一入口(選用)
tools/check_layers.py       從 fastapi-master 的 scripts/ 複製
```

依賴只能由外向內。把 `tools/check_layers.py` 包成 `tests/architecture/test_layers.py`,
違規時直接紅燈,不要靠自律。

幾條在本專案特別容易踩的:

- **共用的基礎設施 provider 放 `core/dependencies.py`,不要放在某個領域的 presentation**。
  session factory、clock、限流是全服務共用的,掛在某個領域底下會讓別的領域被迫跨域 import。
- **跨領域的 adapter 在 composition root(`main.py`)組好掛上 `app.state`**,
  presentation 只認自己領域定義的 port——連對方 `api` 的名字都不該出現在 presentation。
- **實體不是 ORM model**。資料表要照 `01_資料模型與儲存規格.md` 第 2.0 節的慣例
  (uuid PK、timestamptz、`text + CHECK`、每表都有 created_at/updated_at),
  那些是儲存的事;業務模型不必跟著長。中間用 mapper。
- **介面一律 ABC + `@abstractmethod`,實作明確繼承**。每個介面都要有正式實作與 fake,
  兩者跑同一份合約測試。

## Phase 2:TDD(由內而外)

一次一個行為,順序:domain → 定介面 → fake + 合約測試 → application(用 fake)
→ presentation(override port)→ infrastructure(正式實作跑同一份合約測試)。
1~5 都不需要資料庫,紅綠循環最短。

- 紅燈原因必須是「功能未實作」。`ImportError`、fixture 壞掉不算——先修測試本身。
- 沒辦法自然走出紅燈時(例如補了例外類別後直接綠了),做一次**變異檢查**:暫時把
  關鍵那行拿掉,確認測試真的會紅,再還原。不要假裝有紅燈。
- 測試名稱用業務語言,docstring 標註對應的規格章節或審查編號,日後可追溯。
- 業務規則在 domain 測試窮盡;application 測流程編排(載入、權限、呼叫實體、commit);
  presentation 只測 HTTP 契約;查詢/排序/分頁/游標是 infrastructure 的責任。

## 本專案的固定規範

**對外契約**:`interfaces/backend/<service>/__init__.py` 是給其他服務與規格書讀的,
對應實作的 **domain 層**。實作偏離它就要同步更新,並用 `tests/test_contract.py` 讓走樣
當場紅燈。比較時要抹平「契約用 `from __future__ import annotations`、實作沒有」造成的
型別字串差異。

**錯誤回應**:一律 `{"error": {"code": "...", "message": "..."}}`。領域例外只宣告
業務分類與錯誤碼(`AUTH_*`、`VAL_001`、`RATE_001`、`SRV_*`,以及各功能的 `DRIVE_`、
`STREAM_`、`CLIP_` 等前綴),狀態碼對應集中在 `core/http_errors.py`。
本專案偏離通用預設的一點:`BusinessRuleViolation` 對到 **400** 而不是 422,因為
`10_錯誤處理與狀態規範.md` 第 3 節明定 `VAL_001` 是 400。
**找不到與無權限回同一個 404**,不回 403——不洩漏資源存在性。

**CAP 降級**:照 ADR 第 4 節的逐服務判斷,不要自己另外決定。規則是**會寫入 Postgres
的操作一律選 C(寧可失敗)**;純讀取且有快取可退才選 A。Redis 依用途分別處理——
限流 fail-open,安全相關(OAuth state、session)fail-closed。

**資料庫**:目前**不連真實 DB**。ORM model 依 `01_資料模型與儲存規格.md` 定義,
需要 PostgreSQL 的測試標記 `integration` 並在 `pyproject.toml` 以
`addopts = "-m 'not integration'"` 預設關掉。**不要用 SQLite 代替**——tuple 比較的
游標、timestamptz 邊界、`DELETE ... RETURNING` 正是 SQLite 的寬鬆行為會蓋掉的地方。
需要的 schema 變更寫進該服務 README 的「待辦:建立資料庫」,不要自己偷偷建表或寫
migration;等所有服務規格確認後,再依 `postgres-db-master` 一次產出。

**技術預設**:Python 3.12+、FastAPI、Pydantic v2(**只在 presentation**)、
SQLAlchemy 2.0 async(**只在 infrastructure**)、`pydantic-settings`、`lifespan`、
`uv`、`pytest` + `pytest-asyncio`(`asyncio_mode = "auto"`)、
`httpx.AsyncClient` + `ASGITransport`(不用 `TestClient`)、`ruff` + `mypy`、UUIDv7。

## Phase 3:收尾

```bash
uv run pytest --cov=app --cov-report=term-missing   # domain/application 應接近 100%
uv run python tools/check_layers.py --root .
uv run ruff check app tests
uv run mypy app
```

未覆蓋的行要逐條說明原因(通常是 infrastructure 與 wiring,會被 `-m integration`
補上)。最後產出:規格條目 ↔ 測試對照表、採用的假設、已知限制、建議的下一步。
