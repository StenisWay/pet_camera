# Media 服務(F5:剪輯與截圖)

擁有 `media_items` 表的**寫入端**:使用者主動從鏡頭畫面擷取的截圖與剪輯,由本服務
建立並推進處理狀態。相簿的瀏覽、刪除、Google Drive 匯出屬 Album 服務
(見 `../album/`),兩者共用同一張表——這是本專案唯一沒有做到「一服務一資料表」
的例外,理由見 `rule_doc/功能需求/13_ADR_微服務與三節點部署.md` 第 1 節。

對應規格:`rule_doc/功能需求/11_spec_剪輯與截圖.md`
對外契約:`__init__.py`

## 跑起來

```bash
uv sync
uv run pytest                      # 預設不需要資料庫
uv run pytest -m integration       # 需要 PostgreSQL(TEST_DATABASE_URL 或 Docker)
uv run ruff check app tests
uv run mypy app
uv run python tools/check_layers.py --root .
uv run uvicorn app.main:app --reload
```

## 結構

依業務領域切分,領域內四層,依賴只能由外向內(與 `../album/` 一致)。

```
app/
├── main.py                    composition root:adapter 在 lifespan 建好掛上 app.state
├── orm_models.py
├── shared_kernel/             純 Python:錯誤分類、Clock / IdGenerator 介面
├── core/                      框架與基礎設施:config、database、http 錯誤轉換、security、限流
└── domains/media/
    ├── domain/                MediaItem、ClipRange、SourceEvent、R2 key 規則、repository 介面
    ├── application/           use case、DTO、port(UnitOfWork / 四個外部系統)
    ├── infrastructure/        ORM、mapper、SQLAlchemy repository、R2 / Event / Device / worker adapter
    └── presentation/          FastAPI router、Pydantic schema、組裝點
```

只有一個領域,不拆成 `capture` + `clip`:兩者寫的是同一個聚合、同一條狀態機、會一起
變動。拆開等於讓兩個領域宣稱擁有同一個聚合,正是 ADR 第 1 節批評的那種切法。

## 這個服務依賴誰

全部走 VCN 私有網路、不經 Load Balancer,以共享金鑰標頭把關:

| 對象 | 用途 | 端點 |
|---|---|---|
| Event 服務 | 取得剪輯/回放截圖的來源事件(含 `owner_id`) | `GET /internal/events/{id}` |
| Device 服務 | 確認鏡頭擁有者與線上狀態 | `GET /internal/devices/{id}` |
| VM-3 worker | 擷幀、剪輯轉碼 | `POST /internal/frames`、`POST /internal/clips` |
| ← VM-3 worker | 完成/失敗回呼 | `POST /internal/media/{id}/ready`、`/failed` |

application 層只依賴自己定義的 port(`EventSource`、`DeviceDirectory`、`FrameSource`、
`ClipWorker`、`MediaStorage`),adapter 在 infrastructure,測試一律注入 fake。

## 規格審查結論

開發前對 `11_spec` 做了對抗式審查,列出 8 項阻斷、7 項重要、4 項建議問題,
使用者確認「都照建議」。完整決議表寫回了 `11_spec` 第 7 節,這裡只記與程式碼直接
相關的幾項:

- **截圖同步、內部仍先寫 `processing`**:R2 key 含 `media_item_id`,必須先有 id 才
  算得出 key;先上傳再寫 DB 會在 DB 失敗時留下孤兒檔案。
- **剪輯上限 60 秒**(原訂 5 分鐘)。事件最長錄影 60 秒且不支援跨事件合併,
  5 分鐘的上限永遠觸發不到,`CLIP_003` 與對應驗收標準都會是死的。
- **保留期以 `events.started_at + 7 天` 判定**,不打 R2。DB 判定比實際保守,
  方向是對的;判定未過期但檔案已刪時由 worker 失敗走 `CLIP_002`。
- **非擁有者一律 404**,不回 403,不洩漏資源存在性。
- **`processing` 逾時 15 分鐘改判 `failed`**,與 F6 的 `exporting` 對稱。
- **上游服務故障回 `SRV_002`(503)**(實作時補的假設,規格未寫):Device 或 Event
  服務連不上、回 5xx 時,adapter 拋 `ServiceUnavailable`,不讓原始 `httpx` 例外變成
  沒有錯誤碼的 500。worker 擷幀失敗仍依規格回 `SCREENSHOT_001`。
- **剪輯冪等**:以 `(user_id, source_event_id, captured_at, duration_sec)` 去重,
  不新增欄位存起訖秒數——`captured_at` 已是事件開始 + `start_sec`。

### 對外契約 `__init__.py` 的修改

原介面有兩個問題無法實作:`object_key` 宣告為必填(連 `processing` 狀態的項目都建
不出來)、`get_by_id` 沒有擁有者參數(等於 IDOR)。修改清單見該檔頭。

## 測試

```
規格條目                                   測試
11_spec §2.1 截圖同步完成                  application/test_take_live_screenshot.py
11_spec §2.1 回放截圖時間點                application/test_take_event_screenshot.py
11_spec §2.2 剪輯檢核與派工                application/test_request_clip.py
11_spec §2.2 剪輯長度與範圍                domain/test_clip_range.py
11_spec §2.2 來源保留期與 ready            domain/test_source_event.py
11_spec §2.3 逾時收斂                      application/test_lifecycle.py
11_spec §2.5 限流與 fail-open              core/test_rate_limit.py
11_spec §3   HTTP 契約、錯誤碼、權限       presentation/test_api.py
11_spec §3.1 worker 回呼                   application/test_lifecycle.py、e2e/test_clip_flow.py
資料模型 §2.4 狀態機與欄位規則             domain/test_media_item.py
資料模型 §3.1 R2 key 命名                  domain/test_object_keys.py
repository 行為承諾(fake 與 SQLAlchemy)  contracts/test_media_item_repository_contract.py
跨服務 adapter 的回應轉換與故障處理       infrastructure/test_http_adapters.py
分層依賴、介面實作、對外契約               architecture/、test_contract.py
```

`pytest` 預設跑 163 個測試,不需要任何外部服務;另有 14 個標記 `integration` 的測試
需要真實 PostgreSQL。

domain 與 application 層覆蓋率 100%。跨服務的 HTTP adapter(Device、Event、worker)以
`httpx.MockTransport` 測試;仍未覆蓋的是 R2 adapter、SQLAlchemy repository 與
`main.py` 的 wiring——它們需要真實外部系統,或只在整合測試裡才有意義。

## 待辦:建立資料庫

目前**不連任何真實資料庫**。`app/domains/media/infrastructure/orm.py` 是
`media_items` 的權威 schema 定義(本服務是該表的擁有者),但建表與 migration 等
所有服務的規格都確認後再一次產出,統一放在專案根的 `db/`。

屆時需要注意的差異:

1. **跨服務外鍵不在本服務的 ORM 裡**:`user_id → users`、`device_id → devices`、
   `source_event_id → events` 分屬 Auth、Device、Event 服務,不在本服務的 metadata
   中。FK 與各自的 `ON DELETE` 行為(CASCADE / RESTRICT / SET NULL,見資料模型
   §2.4、§6)要寫在共用 migration 裡。
2. **`photo` 也可以有縮圖**:資料模型 §2.4 原訂 `photo` 的 `thumbnail_object_key`
   必為 null,已依審查決議 #17 放寬,文件已同步更新。
3. **`updated_at` 由 trigger `set_updated_at()` 維護**:本服務的 mapper 不寫這一欄,
   逾時掃描直接讀它。
4. **Album 的兩個欄位不可由本服務寫入**:`drive_export_status`、`drive_file_id`
   在 ORM 裡有定義(本服務擁有整張表的 schema),但 mapper 刻意不碰——
   碰了就會和 Album 服務互相覆蓋。
