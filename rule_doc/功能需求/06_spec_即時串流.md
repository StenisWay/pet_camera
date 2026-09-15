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

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| POST | `/devices/{device_id}/stream/session` | 建立直播 session,回傳 TURN 憑證 |
| POST | `/devices/{device_id}/stream/offer` | 送出 SDP offer,取得 answer |
| DELETE | `/devices/{device_id}/stream/session/{session_id}` | 結束 session |

## 4. 平台差異

| 項目 | 手機原生 App | Web |
|---|---|---|
| WebRTC 實作 | 原生 WebRTC SDK | 瀏覽器內建 WebRTC API |
| 背景行為 | App 進背景後主動斷線 | 分頁切走/最小化後比照處理 |

## 5. 限制

同一時間僅允許一個觀看端連線同一支鏡頭,第二個連線請求被拒絕。

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
| STREAM_001 | 409 | 鏡頭離線(`devices.status = offline`) | 鏡頭目前離線 | 全頁錯誤,不發起連線 |
| STREAM_002 | 401 | TURN 憑證過期 | 連線逾時,請重新整理 | Toast + 自動重試 |
| STREAM_003 | - | ICE 連線失敗(重試 3 次後) | 無法連線到鏡頭 | 全頁錯誤 + 手動重試按鈕 |
| STREAM_004 | 409 | 已有其他裝置正在觀看 | 目前有其他裝置正在觀看 | 阻斷式提示 |
| STREAM_005 | 408 | Signaling 逾時 | 連線逾時 | Toast + 自動重試 |

若共用 Redis 無法存取導致無法建立或查詢 session,回傳全域錯誤碼 `SRV_002`(見 `10_錯誤處理與狀態規範.md` 第 3 節),不新增專屬錯誤碼;降級規則見 `13_ADR_微服務與三節點部署.md` 第 4 節。

## 8. 驗收標準

- [ ] 使用者開啟直播頁,3 秒內看到畫面
- [ ] 鏡頭離線時顯示 STREAM_001,不發起 WebRTC 流程
- [ ] 網路中斷後自動重試 3 次,失敗後顯示 STREAM_003 並提供手動重試
- [ ] 離開直播頁後,鏡頭端與 TURN session 確實釋放
- [ ] 第二個觀看端連線時顯示 STREAM_004
- [ ] iOS Safari、Android Chrome、桌面 Chrome 皆能完成完整直播流程
