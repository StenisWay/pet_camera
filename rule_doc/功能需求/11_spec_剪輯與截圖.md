# 功能規格書:剪輯與截圖(F5)

| 項目 | 內容 |
|---|---|
| 優先級 | P1 |
| 相依功能 | F1(即時串流)、F2(事件偵測,擷幀與轉碼由其 worker 執行)、F3(時間軸,剪輯來源為歷史事件) |
| 資料模型 | `01_資料模型與儲存規格.md` — `media_items` 表、相簿項目狀態機 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |
| 實作 | `interfaces/backend/media/` |
| 修訂 | 依 2026-09-20 規格審查結論更新第 2、3、5、6 節,並新增第 7 節記錄決議 |

## 1. 使用者故事

1. 作為使用者,我在看即時畫面或歷史事件時,想截一張照片保存下來。
2. 作為使用者,我想從一段歷史錄影裡剪出一小段保存到相簿。

## 2. 功能說明

### 2.1 截圖

使用者於攝影機畫面(即時串流或事件回放)點擊截圖按鈕,後端擷取一幀產生照片檔,
建立 `media_items` 紀錄(`type = photo`)。

**截圖是同步的**:API 回應時項目已是 `status = ready`。內部仍先寫入 `processing`
再轉 `ready`,因為 R2 key 含 `media_item_id`,必須先有 id 才算得出 key;倒過來
(先上傳再寫 DB)會在 DB 失敗時留下無法追蹤來源的孤兒檔案。

影像來源不是本服務:F1 的 WebRTC media 經 TURN 直達前端、不經過後端 API,唯一持有
鏡頭影像的是 VM-3 上直連 RTSP 的事件偵測 worker。Media 服務呼叫 worker 的內部端點
`POST /internal/frames` 取得一幀(含縮圖),再寫入 R2。

- 即時截圖:鏡頭須為已配對且在線(`devices.status = paired`),否則 `SCREENSHOT_001`。
- 事件回放截圖:來源事件須 `status = ready` 且在保留期內(與剪輯相同的前置條件),
  時間點以 `offset_sec`(相對事件開始的整數秒)指定,須落在 `0 ~ duration_sec`。
- 截圖**一併產生縮圖**。相簿網格一次顯示數十個項目,沒有縮圖就得載原圖;
  此處放寬了 `01_資料模型與儲存規格.md` §2.4 原本「photo 的 `thumbnail_object_key`
  必為 null」的限制。

### 2.2 剪輯

使用者於歷史事件回放頁選擇起訖時間點,送出剪輯請求。後端檢核後建立 `media_items`
紀錄(`type = clip`、`status = processing`)並派工給 VM-3 的 worker 非同步裁切,
完成後 worker 回呼內部端點把狀態推進為 `ready` 或 `failed`。

- 起訖以 `start_sec` / `end_sec`(相對事件開始的整數秒)指定,
  須滿足 `0 <= start_sec < end_sec <= 事件的 duration_sec`。
- **單次剪輯長度上限 60 秒**,對齊 F2 §2.2 的單一事件錄影上限。
  (原訂 5 分鐘:因為剪輯來源僅限單一事件影片內,而事件最長 60 秒,5 分鐘的上限
  永遠觸發不到,`CLIP_003` 與對應的驗收標準都會是死的。)
- 剪輯來源僅限單一事件影片內的時間範圍,不支援跨事件合併剪輯。
- 來源影片保留期以 `events.started_at + 7 天` 判定,不額外查詢 R2——
  `videos/` 的 lifecycle rule 是 7 天,但 `events` 紀錄與 `video_object_key` 都會保留,
  「檔案還在不在」無法從資料列看出來。DB 判定會比實際保守(lifecycle 是每日批次,
  可能晚於第 7 天才真正刪除),這個方向是對的:同步回 `CLIP_001` 比讓 worker 跑到
  一半才發現檔案不見好。判定為未過期但 R2 實際已刪時,由 worker 失敗走 `CLIP_002`。
- **重送同一段範圍不重複建立項目**:同一使用者對同一來源事件、同一 `captured_at`
  與長度、且仍在 `processing` 或 `ready` 的剪輯,直接回傳既有項目。
  (`failed` 的不算——使用者重送就是要重試。)

### 2.3 處理逾時

`processing` 停留超過 **15 分鐘**由後端改判 `failed`(`CLIP_002`),與 F6 的
`exporting` 規則對稱。理由相同:背景工作跑在可被 LB 隨時汰換的無狀態複本上,
複本重啟後進行中的任務就消失了,沒有這道收斂,相簿卡片會永遠轉圈。
判定直接用 `media_items.updated_at`,不另外增加欄位。

### 2.4 權限

四個對外端點都需要登入,`user_id` 取自 access token,不接受由 request body 帶入。
鏡頭、事件、相簿項目一律驗證擁有者;**不屬於本人時回傳與「不存在」完全相同的
回應(404)**,不回 403,避免洩漏資源存在性。

`events` 表沒有 `user_id`,擁有者由 Event 服務的內部端點連同事件一起回傳。

### 2.5 限流

擷幀與 ffmpeg 轉碼吃的是 VM-3 的 2 OCPU,是全系統唯一的瓶頸(`13_ADR` 第 6 節),
因此本功能的限流比其他服務嚴格:

| 操作 | 額度 |
|---|---|
| 截圖(即時 + 回放) | 10 次 / 分鐘 / 使用者 |
| 剪輯 | 3 次 / 分鐘 / 使用者 |

逾量回 `RATE_001`。計數與 fail-open 行為依 `10_錯誤處理與狀態規範.md` 第 3 節。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| POST | `/devices/{device_id}/screenshot` | 即時畫面截圖,`201`,回傳已 `ready` 的項目 |
| POST | `/events/{event_id}/screenshot` | 事件回放截圖,body `{"offset_sec": int}`,`201` |
| POST | `/events/{event_id}/clip` | 剪輯請求,body `{"start_sec": int, "end_sec": int}`,`202` 表示已受理 |
| GET | `/media/{media_item_id}` | 查詢處理狀態與內容,`200` |

回應僅 `status = ready` 的項目夾帶效期 10 分鐘的 presigned URL(內容與縮圖各一),
不外洩 R2 object key。前端在相簿頁對 `processing` 的項目每 5 秒輪詢一次,最多 15 分鐘
(對應第 2.3 節的逾時)。

**路由邊界**:`GET /media`、`DELETE /media/{id}`、`POST /media/export/google-drive`
屬 Album 服務(`12_spec` 第 3 節),Load Balancer 依此分流。

### 3.1 內部端點(不經 Load Balancer,共享金鑰標頭把關)

| Method | Path | 方向 | 說明 |
|---|---|---|---|
| POST | `/internal/media/{id}/ready` | worker → Media | 轉檔完成,附 object key |
| POST | `/internal/media/{id}/failed` | worker → Media | 轉檔失敗 |
| POST | `/internal/frames` | Media → worker | 擷取一幀(含縮圖) |
| POST | `/internal/clips` | Media → worker | 派工裁切,附起訖秒數與目標 object key |
| GET | `/internal/events/{id}` | Media → Event | 取得來源事件,**回應須含 `owner_id`** |
| GET | `/internal/devices/{id}` | Media → Device | 取得鏡頭擁有者與狀態 |

刻意不引入工作佇列:`13_ADR` 第 1.1 節把共用 Redis 的用途限定在三項,不含佇列。
派工是一次同步的內部 HTTP 呼叫(受理即回),不擴大 Redis 的職責範圍。

## 4. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 點擊截圖按鈕 | 按鈕短暫 disable,截圖成功以 Toast 提示「已保存至相簿」 |
| 送出剪輯請求後 | 顯示「處理中」提示並停留於當前頁面,不阻塞其他操作(背景處理) |
| 相簿內對應項目 | `status = processing` 時卡片顯示 spinner + 「處理中」;`ready` 後可正常瀏覽播放 |

## 5. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| CLIP_001 | 410 | 剪輯來源影片已過保留期、不存在,或尚未處理完成 | 此片段已無法剪輯 | Toast |
| CLIP_002 | 503 / - | 剪輯處理失敗。派工當下失敗回 503;轉碼階段失敗則無 HTTP 回應,反映為項目的 `failed` 狀態 | 剪輯失敗,請重試 | 相簿卡片內嵌錯誤圖示 |
| CLIP_003 | 400 | 剪輯長度超過 60 秒上限 | 單次剪輯最長 60 秒 | Inline 於剪輯時間選取元件 |
| SCREENSHOT_001 | 503 | 截圖來源不存在、鏡頭離線或 worker 無回應 | 截圖失敗 | Toast |

起訖秒數本身不合法(負數、顛倒、超出來源影片長度、型別錯誤)回全域 `VAL_001`;
`CLIP_003` 只保留給超過長度上限。找不到與無權限一律 404。

服務複本連不到 VM-3 的 Postgres 時,所有寫入操作回 `SRV_002`(選一致性),
詳見 `13_ADR_微服務與三節點部署.md` 第 4 節。

## 6. 驗收標準

- [ ] 使用者可在即時畫面截圖,API 回應時項目已是 `ready`,相簿可查詢到該照片
- [ ] 使用者可在歷史事件回放指定秒數截圖,`captured_at` 為事件時間 + offset
- [ ] 使用者可從歷史事件剪輯出指定時間範圍的短片,完成後相簿可查詢到該剪輯
- [ ] 剪輯長度超過 60 秒時顯示 CLIP_003,無法送出
- [ ] 剪輯來源已過保留期或非 `ready` 時顯示 CLIP_001,不可發起剪輯
- [ ] 起訖秒數不合法時顯示 VAL_001,且不建立任何相簿項目
- [ ] 重送同一段範圍不會產生第二個相簿項目
- [ ] 剪輯/截圖處理中時,相簿卡片顯示處理中狀態,且 API 不回傳內容連結
- [ ] 任一處理失敗時項目收斂為 `failed`,不會停留在 `processing`
- [ ] `processing` 超過 15 分鐘被改判為 `failed`
- [ ] 對他人的鏡頭、事件、相簿項目操作一律得到 404
- [ ] 超過限流額度時回 RATE_001

## 7. 規格審查決議(2026-09-20)

開發前的對抗式審查列出 8 項阻斷、7 項重要、4 項建議問題,使用者確認「都照建議」。
影響其他文件或服務的決議記錄於此:

| # | 決議 | 連帶影響 |
|---|---|---|
| 1 | 截圖同步完成,`SCREENSHOT_001` 補 503 | 本文件 §2.1、§5 |
| 2 | 擷幀由 VM-3 worker 提供內部端點 | worker 需新增 `POST /internal/frames` |
| 3 | 剪輯派工走內部 HTTP + 完成回呼,不引入佇列 | worker 需新增 `POST /internal/clips`;不擴大 `13_ADR` §1.1 的 Redis 範圍 |
| 4 | 剪輯上限由 5 分鐘改為 60 秒 | 本文件 §2.2、§5、§6 |
| 5 | 時間點一律用相對事件開始的整數秒 | 本文件 §3 |
| 6 | 非擁有者一律 404,不新增 403 錯誤碼 | 本文件 §2.4 |
| 7 | Event 服務新增 `GET /internal/events/{id}`,回應含 `owner_id` | **`07_spec` / `08_spec` 待補**:Event 服務需實作此端點 |
| 8 | 保留期以 `started_at + 7 天` 在 DB 判定 | 同一個判定缺口也存在於 F3 的 `TIMELINE_002`,`08_spec` 待補 |
| 9 | `processing` 逾時 15 分鐘改判 `failed` | 本文件 §2.3 |
| 10 | 剪輯以 `(user_id, source_event_id, captured_at, duration_sec)` 去重 | 不新增資料表欄位 |
| 11 | `captured_at` 取事件時間 + offset,非按鈕按下時間 | 本文件 §2.1、§2.2 |
| 15 | 截圖 10 次/分、剪輯 3 次/分 | 本文件 §2.5 |
| 16 | 對外契約 `media/__init__.py` 依實作修正 | 見該檔頭的修改清單 |
| 17 | 截圖一併產生縮圖 | **`01_資料模型與儲存規格.md` §2.4 待更新**:photo 的 `thumbnail_object_key` 不再強制為 null |
