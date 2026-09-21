# 功能規格書:即時串流(F1)

| 項目 | 內容 |
|---|---|
| 優先級 | P0 |
| 相依功能 | F0 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |
| NFR | 首幀出現時間 < 3 秒 |

## 1. 使用者故事

作為飼主,我想要在 App 或 Web 打開鏡頭頁面後,盡快看到現場即時畫面。

## 2. 功能說明

使用 WebRTC 建立 App/Web 與鏡頭之間的即時影音連線,連線經由 TURN server 中繼。

### 2.1 流程

1. 使用者開啟指定鏡頭的直播頁面。
2. 前端向 Backend API 請求 TURN 短效憑證與 signaling session。
3. 前端與鏡頭端透過 Backend 交換 SDP offer/answer、ICE candidate。
4. 連線建立後,影音經 TURN 中繼(或 P2P 成功時直連)傳輸到前端播放。
5. 使用者離開頁面時結束連線,釋放鏡頭端與 TURN 資源。

Session 狀態(TURN 憑證、SDP offer/answer 交換過程)存於共用 Redis(`stream:session:{session_id}`,見 `01_資料模型與儲存規格.md` 第 7 節),不存在服務本機記憶體。原因:兩台 VM 各跑一份 Stream 訊令服務複本,Load Balancer 以請求為單位分流,同一個 session 的「建立 session」「送出 offer」「結束 session」三個請求可能被分派到不同複本;若狀態存在本機記憶體,跨複本讀不到會導致連線隨機失敗,必須靠 Redis 做共享暫存。

### 2.2 畫質

固定 720p、約 2 Mbps,不做自適應碼率。

### 2.3 斷線與重連

前端偵測到 ICE connection 狀態變為 `disconnected`/`failed` 時,自動重試 3 次,間隔 2s/4s/8s。3 次全部失敗後停止重試並顯示錯誤。

### 2.4 Session 生命週期與接管

Session 存於 Redis(`stream:session:{session_id}`),TTL **300 秒**;另存
`stream:device:{device_id}` -> `session_id` 的索引(同 TTL),供「目前誰在看」查詢與接管。

**接管語意**:同一支鏡頭已有 session 時,新的 `POST .../stream/session` **直接接管**
——覆寫裝置索引、刪除舊 session 後建立新的,回 201,不回 `STREAM_004`。理由:

1. `devices.user_id` 是單一擁有者,「其他裝置正在觀看」必然是同一位飼主的另一台裝置,
   把他自己擋在門外沒有業務意義。
2. App 閃退、斷網、分頁直接關閉時不會呼叫 DELETE,殘留 session 會把使用者鎖死到 TTL 到期。
3. `screens/app/04_page_攝影機畫面.md` 第 3 節規定「即時 / 歷史」分頁切換即視為離開直播並
   重新建立連線,頻繁切換必然撞上尚未釋放的舊 session。

接管使「同一裝置同時只有一個 session」變成單一 Redis key 的覆寫(last-writer-wins),
不需要分散式鎖,也消除了兩個並發建立請求的競態。

`STREAM_004` 保留不刪除,供未來「鏡頭共享給多位使用者」時使用;現階段不會被觸發。

### 2.5 TURN 憑證

採 coturn 的 REST API 認證(`use-auth-secret` + `static-auth-secret`):

- `username = "{expiry_unix_ts}:{session_id}"`,`expiry` 為簽發時間 + **600 秒**
- `credential = base64(HMAC_SHA1(TURN_STATIC_SECRET, username))`
- `urls` 由設定檔提供,內容固定為 `14_API閘道與路由規範.md` 第 2.1 節列出的三筆(TURN server 為單例,固定在 VM-3,見 `13_ADR_微服務與三節點部署.md`)

密鑰以環境變數 `TURN_STATIC_SECRET` 注入,不進版控。憑證有效期(600s)刻意長於 session
TTL(300s),因此不會出現「session 還在、但 TURN 憑證先過期」的狀態。

## 3. API 介面

### 3.1 觀看端(App / Web,需登入)

| Method | Path | 說明 |
|---|---|---|
| POST | `/devices/{device_id}/stream/session` | 建立直播 session,回傳 `session_id` 與 TURN 憑證 |
| POST | `/devices/{device_id}/stream/offer` | 送出 SDP offer(body 帶 `session_id`),同步等待鏡頭端 answer,逾時 5 秒 |
| POST | `/devices/{device_id}/stream/candidates` | 送出觀看端 ICE candidate(body 帶 `session_id`) |
| GET | `/devices/{device_id}/stream/candidates?session_id=&since=` | 取回鏡頭端 ICE candidate |
| DELETE | `/devices/{device_id}/stream/session/{session_id}` | 結束 session(冪等,一律 204) |

### 3.2 鏡頭端(`/internal` 前綴,經 Load Balancer 對公網開放,以裝置憑證把關)

原規格第 2.1 節要求「前端與鏡頭端透過 Backend 交換 SDP offer/answer、ICE candidate」,
但原 API 表只有觀看端。以下補齊鏡頭端那一半,否則 signaling 不成立:

| Method | Path | 說明 |
|---|---|---|
| GET | `/internal/devices/{device_id}/stream/pending-offer` | 長輪詢取得待處理的 offer,逾時 30 秒回 204 |
| POST | `/internal/devices/{device_id}/stream/answer` | 回覆 SDP answer(body 帶 `session_id`) |
| POST | `/internal/devices/{device_id}/stream/candidates` | 送出鏡頭端 ICE candidate |
| GET | `/internal/devices/{device_id}/stream/candidates?session_id=&since=` | 取回觀看端 ICE candidate |

採 HTTP 長輪詢而非 WebSocket:與其餘六個服務的 HTTP 形狀一致,不需要為 WebSocket
調整 Load Balancer 的連線黏性(見 `13_ADR_微服務與三節點部署.md` 第 3 節)。

### 3.3 權限

| 端點群 | 呼叫者 | 驗證方式 |
|---|---|---|
| 3.1 觀看端 | 已登入使用者 | JWT;且 `devices.user_id` 必須等於呼叫者 |
| 3.2 鏡頭端 | 鏡頭硬體 | 裝置憑證,機制比照 `/devices/{device_id}/heartbeat`(見第 9 節待確認事項) |

- 未登入或 token 無效 -> `AUTH_001`(401)。
- 裝置不存在、未配對(`status = pending`)、或不屬於呼叫者,**一律回同一個
  `DEVICE_005`(404)**,不回 403——不洩漏裝置存在性。
- DELETE 時 `session_id` 必須屬於呼叫者,否則同樣回 `DEVICE_005`。

## 4. 平台差異

| 項目 | 手機原生 App | Web |
|---|---|---|
| WebRTC 實作 | 原生 WebRTC SDK | 瀏覽器內建 WebRTC API |
| 背景行為 | App 進背景後主動斷線 | 分頁切走/最小化後比照處理 |

## 5. 限制

同一時間僅允許一個觀看端連線同一支鏡頭。第二個連線請求的處理方式見第 2.4 節
「接管語意」——同一位擁有者直接接管舊連線,不拒絕。

## 6. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 進入頁面,尚未建立連線 | 鏡頭縮圖佔位圖 + 中央 spinner + 「連線中...」文字 |
| Signaling / ICE 協商中 | 維持 spinner 疊加層 |
| 首幀渲染完成 | 移除 loading 疊加層,顯示畫面 |
| 自動重連中 | 畫面上疊加半透明「重新連線中...」提示,不整頁替換為 loading |

## 7. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| STREAM_001 | 409 | 鏡頭離線(`devices.status = offline`,或 `last_seen_at` 距今超過 90 秒,見 `03_spec_裝置配對.md` 第 2.3 節) | 鏡頭目前離線 | 全頁錯誤,不發起連線 |
| STREAM_002 | 401 | Session 已失效——TTL 到期或已被接管,帶著失效的 `session_id` 呼叫 offer / answer / candidates 時回傳 | 連線逾時,請重新整理 | Toast + 自動重試 |
| STREAM_003 | - | ICE 連線失敗(重試 3 次後)。**純前端判定,不對應任何 API 回應** | 無法連線到鏡頭 | 全頁錯誤 + 手動重試按鈕 |
| STREAM_004 | 409 | 已有其他裝置正在觀看。**現階段不會觸發**,見第 2.4 節 | 目前有其他裝置正在觀看 | 阻斷式提示 |
| STREAM_005 | 408 | Signaling 逾時:`POST .../stream/offer` 等待鏡頭端 answer 超過 5 秒 | 連線逾時 | Toast + 自動重試 |
| DEVICE_005 | 404 | 裝置不存在、未配對或不屬於呼叫者(沿用 `04_spec_裝置管理.md`,不另立新碼) | 找不到此裝置 | 導回裝置列表 + Toast |

`STREAM_002` 的語意在規格審查中修正:原文寫「TURN 憑證過期」,但 TURN 憑證是由 TURN
server 在建立媒體連線時驗證,Backend 的 HTTP API 不可能產生該錯誤。且依第 2.5 節,
憑證效期(600s)長於 session TTL(300s),先到期的必定是 session。

若共用 Redis 無法存取導致無法建立或查詢 session,回傳全域錯誤碼 `SRV_002`(見
`10_錯誤處理與狀態規範.md` 第 3 節),不新增專屬錯誤碼;降級規則見
`13_ADR_微服務與三節點部署.md` 第 4 節。**例外**:`DELETE .../stream/session/{id}`
採 fail-open,Redis 不可用時仍回 204——session 本來就會因 TTL 自動消失,讓使用者
在離開頁面時收到 503 沒有意義。

## 8. 驗收標準

- [ ] 使用者開啟直播頁,3 秒內看到畫面
- [ ] 鏡頭離線時顯示 STREAM_001,不發起 WebRTC 流程
- [ ] 網路中斷後自動重試 3 次,失敗後顯示 STREAM_003 並提供手動重試
- [ ] 離開直播頁後,鏡頭端與 TURN session 確實釋放
- [ ] 同一位擁有者的第二個觀看端連線時,舊連線被接管中斷,新連線正常播放(第 2.4 節)
- [ ] iOS Safari、Android Chrome、桌面 Chrome 皆能完成完整直播流程


## 9. 規格審查決議(2026-09-20)

實作 `interfaces/backend/stream/` 前的規格審查結論。以下為本次新增或修正的部分:

| # | 原問題 | 決議 |
|---|--------|------|
| 1 | `POST .../stream/offer` 無 session 識別,Redis key 是 `stream:session:{id}`,靠 device_id 反查不到 | body 帶 `session_id`;新增 `stream:device:{device_id}` 索引(第 2.4 節) |
| 2 | 單一觀看端限制沒有釋放條件,殘留 session 會鎖死使用者自己 | 改為同一擁有者**接管**;TTL 300 秒(第 2.4 節、第 5 節) |
| 3 | 三個端點均未定義呼叫者與擁有者驗證,存在 IDOR | 新增第 3.3 節;查無與無權限一律 `DEVICE_005` 404 |
| 4 | 鏡頭端 signaling 端點完全缺失,ICE candidate 無交換管道 | 新增第 3.2 節內部路由,採 HTTP 長輪詢 |
| 5 | TURN 憑證產生方式未定義;`STREAM_002` 與實際流程矛盾 | 新增第 2.5 節 coturn REST 認證;`STREAM_002` 改為「session 失效」(第 7 節) |
| 6 | `STREAM_005` 逾時門檻未量化 | offer 等待 answer 逾時 5 秒(第 3.1、7 節) |
| 7 | 無人將 `paired` 轉為 `offline`,`STREAM_001` 可能永不觸發 | Stream 側改為同時檢查 `last_seen_at` 是否超過 90 秒(第 7 節) |
| 8 | Redis 不可用時 DELETE 的行為未定義 | DELETE 採 fail-open 回 204(第 7 節) |
| 9 | 重複 DELETE 的行為未定義 | 冪等,一律 204(第 3.1 節) |
| 10 | 建立 session 是昂貴操作但無限流參數 | 每位使用者每分鐘 10 次,超過回 `RATE_001`(第 3.1 節) |

### 待確認事項(不阻斷本次實作)

- **鏡頭端認證機制尚未定義**:`03_spec_裝置配對.md` 第 2.3 節的
  `POST /devices/{device_id}/heartbeat` 同樣沒有寫鏡頭如何證明自己的身分。這是跨規格書
  的共同缺口,不是 Stream 專屬。本服務先以一個可替換的介面表達「驗證鏡頭身分」,待
  Device 服務決定機制(裝置 token / mTLS)後接上,不影響其餘各層。
- **NFR「首幀出現時間 < 3 秒」** 是端到端指標,Backend 無法在單元測試中驗證。本服務可
  被測的承諾改寫為:`POST .../stream/session` 的 P95 < 200ms(不含 TURN 與 ICE 協商)。
  首幀 3 秒留給前端 E2E 驗收。
