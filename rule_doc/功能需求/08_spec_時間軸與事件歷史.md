# 功能規格書:時間軸與事件歷史瀏覽(F3)

| 項目 | 內容 |
|---|---|
| 優先級 | P0 |
| 相依功能 | F2 |
| 資料模型 | `01_資料模型與儲存規格.md` — `events` 表、狀態機 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |

## 1. 使用者故事

作為飼主,我想滑一下時間軸,快速看過哪些時段寵物有動靜,並點開片段觀看。

## 2. 功能說明

### 2.1 列表行為

依 `started_at` 由新到舊排序,cursor-based 分頁(`started_at` + `id` 組合游標),支援依日期篩選。每筆項目顯示縮圖、時間、信心分數、已讀/未讀狀態。

列表**回傳全部三種 `status`**(`processing` / `ready` / `failed`),不只 `ready`——時間軸卡片本來就要呈現處理中與失敗狀態,見 `07_spec_事件偵測與自動錄影.md` 第 4 節。

**篩選參數**:`date=YYYY-MM-DD` 搭配 `tz`(IANA 時區名稱,預設 `Asia/Taipei`)表示單日;`from`/`to`(Unix timestamp,秒)表示區間,供 Web 版「過去一個月」的側欄列表使用(見 `screens/web/04_page_攝影機畫面.md` 第 2 節)。`date` 與 `from`/`to` 互斥,同時給定回 `VAL_001`。資料以 UTC 儲存,單日的邊界依 `tz` 換算——不指定時區的話,跨日事件會落在錯誤的那一天。

**分頁**:`limit` 預設 20、上限 100,超過上限回 `VAL_001`。游標是 `(started_at, id)` 的 base64 組合游標:同一秒可能有多筆事件,只靠 `started_at` 分頁會在捲動時重複或遺漏,與 `12_spec_相簿與雲端匯出.md` 第 2.1 節是同一個理由。

**時間格式**:回應中所有時間欄位(`started_at`、`ended_at`、`created_at`)一律為 **Unix timestamp**(秒,整數,UTC 基準)。資料庫仍以 `timestamptz` 儲存(第 2.0 節),epoch 只是對外的呈現格式,兩者不衝突。

**縮圖**:列表回應直接夾帶該事件縮圖的 presigned URL(`thumbnail_url`,有效期 10 分鐘)。R2 不是公開 bucket,不夾帶的話前端根本拿不到圖;一頁 20 筆再逐一去換發 URL 也不合理。縮圖尚未產生(`processing`)或已過 30 天保留期時為 `null`,前端顯示佔位圖示(`TIMELINE_004`)。

### 2.2 播放行為

使用者點擊事件,前端向 Backend API 請求播放連結。Backend 依序檢查:

1. 事件所屬裝置目前屬於呼叫者(見第 3.2 節),否則回 `DEVICE_005`(404)。
2. `status = ready`。`processing` 回 `TIMELINE_005`(409),`failed` 回 `EVENT_001`(409)。
3. 影片未過保留期,即 `started_at + 7 天` 仍在未來,否則回 `TIMELINE_002`(410)。

三項都通過才換發 presigned URL(有效期 10 分鐘)。前端使用支援 range request 的 video 元件播放。

**保留期判定基準**:影片 `started_at + 7 天`、縮圖 `started_at + 30 天`,與 `01_資料模型與儲存規格.md` 第 3.2 節的 R2 lifecycle rule 同一個基準——R2 key 本來就以事件日期分層。資料庫不另外存 `expires_at`:保留期是 lifecycle rule 的推論結果,存一份下來就會有兩個真相來源,且兩者遲早不一致。

presigned URL **無法做到真正的一次性**——URL 在有效期內可以重複使用,這是 S3 相容簽章的性質,不是實作選擇。因此規格上的承諾是「短效」而非「一次性」:10 分鐘到期即失效。

### 2.3 已讀狀態

播放某事件後標記 `is_read = true`。

`PATCH /events/{event_id}` 的 request body **只接受 `{"is_read": bool}`**,其餘欄位一律拒絕(`VAL_001`)——否則使用者可以透過 body 改到 `status`、`confidence_score` 這類不該由用戶端決定的欄位。允許改回 `false`(誤點後標記未讀)。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| GET | `/devices/{device_id}/events?cursor=&limit=&date=&tz=&from=&to=` | 取得事件列表 |
| GET | `/events/{event_id}/playback-url` | 換發影片 presigned URL |
| PATCH | `/events/{event_id}` | 標記已讀(body 只接受 `is_read`) |
| DELETE | `/internal/devices/{device_id}/events` | **內部**:Device 服務移除裝置時串聯清除 |

### 3.1 路由邊界

`/devices` 前綴由 **Device 服務**擁有(見 `04_spec_裝置管理.md` 第 3 節),而七個服務掛在同一個 Load Balancer 後面,因此分流規則要依 method + path 的形狀明確切分,不能只看前綴:

| Path | 導向 |
|---|---|
| `/devices/{id}/events` | Event 服務 |
| `/devices`、`/devices/{id}` | Device 服務 |

### 3.2 擁有者驗證

`events` 表沒有 `user_id`,Event 服務也不擁有 `devices` 表,但三個對外端點都必須確認資源屬於呼叫者——否則任何登入者都能讀取、播放、標記他人的寵物影片(IDOR)。

驗證方式:Event 呼叫 Device 服務的內部端點 `GET /internal/devices/{device_id}`(見 `04_spec_裝置管理.md` 第 3 節)取得該裝置目前的擁有者。`/events/{event_id}` 形狀的端點先以 `event_id` 查出 `device_id`,再走同一套驗證。

**裝置不存在、裝置未配對、或不屬於呼叫者,一律回 `DEVICE_005`(404),不回 403**——403 等於告訴對方「這個 id 確實存在,只是不是你的」,洩漏了資源存在性。

以「裝置目前的擁有者」判斷是安全的:移除裝置會同時刪光該裝置底下所有事件(見 `01_資料模型與儲存規格.md` 第 6 節),所以裝置重新配對給別人時,不會有前一位使用者的事件殘留下來被新擁有者看到。

### 3.3 內部端點:串聯清除

`DELETE /internal/devices/{device_id}/events` 由 Device 服務在移除裝置時呼叫,以 `X-Internal-Api-Key` 把關,只走 VCN 私有網路、不經 Load Balancer(見 `13_ADR_微服務與三節點部署.md` 第 1 節)。

**R2 的影片與縮圖物件由 Event 服務自己刪除**,不交給呼叫端:R2 key 的組成需要 `event_id` 與事件日期(`videos/{device_id}/{yyyy}/{mm}/{dd}/{event_id}.mp4`),而 Device 服務並不知道這個裝置底下有哪些 event,組不出 key。回應回傳刪除的事件筆數。

## 4. 保留期過期後的顯示

影片過期後(7 天)`events` 紀錄仍保留:縮圖仍可顯示(保留 30 天);點擊播放時回傳 TIMELINE_002,前端顯示「影片已過期」。縮圖過期(30 天)後顯示佔位圖示。

過期的判定基準見第 2.2 節:影片 `started_at + 7 天`、縮圖 `started_at + 30 天`。

## 5. 平台差異

| 項目 | 手機原生 App | Web |
|---|---|---|
| 列表捲動 | 原生列表元件,虛擬化捲動 | 自行處理長列表虛擬化 |
| 影片播放 | 原生 video player | `<video>` 標籤,依賴 presigned URL |

## 6. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 首次載入列表 | 3~5 個灰色 skeleton 卡片 |
| 捲動載入更多 | 列表底部小型 spinner |
| 點擊播放 | 播放器內 spinner,直到開始緩衝 |
| 無資料 | 空狀態插圖 + 「目前還沒有偵測到活動」 |

## 7. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| TIMELINE_001 | 500 | 列表載入失敗 | 無法載入事件,請重試 | 全頁錯誤 + 重試按鈕 |
| TIMELINE_002 | 410 | 影片已過保留期 | 影片已過期 | 播放器內提示,非 Toast |
| TIMELINE_003 | 500 | Presigned URL 換發失敗 | 無法播放,請重試 | Inline 於該卡片 |
| TIMELINE_004 | 410 | 縮圖已過期 | (無文字提示) | 顯示佔位圖示 |
| TIMELINE_005 | 409 | 影片尚未就緒(`status = processing`) | 此片段仍在處理中 | 播放器內提示 |

`status = failed` 的事件請求播放時回 `EVENT_001`(409,見 `07_spec_事件偵測與自動錄影.md` 第 5 節),不另外定義時間軸錯誤碼——失敗的原因屬於 F2 的處理流程,時間軸只是把它顯示出來。

**資料層不可用時的降級**:依 `13_ADR_微服務與三節點部署.md` 第 4 節,Event 的讀取選一致性(C)——連不到 Postgres 時回 `SRV_002`(503),**不可回空列表**,否則使用者會誤以為那段時間寵物沒有動靜。`TIMELINE_001`(500)保留給其他非預期的伺服器錯誤。

## 8. 驗收標準

- [ ] 開啟時間軸頁面,1 秒內看到前 20 筆事件列表
- [ ] 捲動列表持續載入更舊事件,無重複或遺漏
- [ ] 點擊未過期事件,1~2 秒內開始播放且能拖拉進度條
- [ ] 已過保留期事件顯示 TIMELINE_002,而非錯誤畫面
- [ ] 依日期篩選正確返回對應範圍事件
- [ ] `status = processing` 的事件不可點擊播放,顯示處理中狀態(見 `07_spec_事件偵測與自動錄影.md` 第 4 節)
- [ ] 非本人的裝置或事件,三個端點一律回 404 DEVICE_005,不回 403
- [ ] `processing` 事件請求播放回 TIMELINE_005,`failed` 回 EVENT_001
- [ ] 資料層不可用時列表回 503 SRV_002,不回空列表
- [ ] 移除裝置後,該裝置的事件紀錄與 R2 影片/縮圖物件皆不存在
