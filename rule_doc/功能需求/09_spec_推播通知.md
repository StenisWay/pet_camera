# 功能規格書:推播通知(F4)

| 項目 | 內容 |
|---|---|
| 優先級 | P1 |
| 相依功能 | F0、F2 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |
| 規格審查 | 2026-09-20 完成,決議見第 8 節,編號對應 `interfaces/backend/push/` 測試 docstring 的「審查 #N」 |

## 1. 使用者故事

作為飼主,我不一定隨時開著 App,希望寵物有動靜時手機能收到通知。

## 2. 功能說明

### 2.1 觸發時機

事件 `status = ready` 後才觸發推播。

觸發者是 **Event 服務的偵測 worker**(`07_spec_事件偵測與自動錄影.md` 第 2.3 節第 6 步):
worker 把事件標記為 `ready` 後,呼叫 Push 服務的內部端點
`POST /internal/notifications/event-ready`(見第 3 節),Push 服務回 `202 Accepted` 後於背景完成
查詢與發送,worker 不等待發送結果——推播失敗不應該拖慢或影響事件本身的處理(審查 #1)。

Push 服務本身不持有裝置資料,收到通知請求後以 `device_id` 向 Device 服務的內部端點
`GET /internal/devices/{device_id}` 取得**裝置名稱與擁有者**(審查 #2)。取即時值而非由
worker 夾帶,是為了讓使用者剛改過的鏡頭名稱立刻反映在通知標題上。

該裝置若**沒有擁有者**(`user_id` 為 `null`,即已解除配對或尚未配對),直接捨棄本次通知,
不發送也不視為錯誤(審查 #13)。使用者名下沒有任何已登記的 push token 時同理。

### 2.2 通知內容

- 標題:「{裝置名稱} 偵測到活動」
- 內容:信心分數描述——`confidence_score >= 0.8` 為「高信心」,否則為「一般」(審查 #7)。
  偵測門檻本身是 0.6(`07_spec` 第 2.1 節),故此處只會出現這兩種描述。
- 附圖:該事件縮圖。以 R2 presigned URL 夾帶,**效期 30 分鐘**——`01_資料模型與儲存規格.md`
  第 3.3 節的 10 分鐘是使用者點播時當下換發,而推播經 APNs/FCM 可能延遲或重送,
  10 分鐘內未送達就會圖裂(審查 #6)。
- 點擊行為:導向該事件播放頁(deep link)。合併通知(第 2.3 節)不指向單一事件,
  改導向該裝置的攝影機畫面(審查 #14)。

### 2.3 防洗版機制

同一裝置 5 分鐘內第一個事件立即推播;窗口內**第二個**事件送出一則合併通知
(標題同上,內容為「偵測到多次活動」),窗口內其餘事件靜默,不再發送。
時間窗結束後有新事件重新開始計算(審查 #3)。

合併通知在第二個事件抵達時立即送出,而非等窗口結束後統計實際次數:Redis key 的 TTL 到期
不會主動喚醒任何程式,「窗口結束才送」需要額外的延遲任務,且 key 過期後計數已不存在、
掃描也讀不到。代價是合併通知不顯示精確次數,故文案為「偵測到多次活動」而非「偵測到 N 次活動」。

此計數窗以共用 Redis 實作(`push:window:{device_id}`,TTL 5 分鐘,見 `01_資料模型與儲存規格.md`
第 7 節),不使用 Postgres,避免高頻寫入增加資料庫負擔。計數以 `INCR` 遞增,
回傳值 1 為首發、2 為合併、3 以上靜默。若 Redis 暫時無法存取,計數窗視為未開始,
依可用性(A)原則直接觸發推播(寧可短暫多推播,不可漏推),降級規則見
`13_ADR_微服務與三節點部署.md` 第 4 節。

### 2.4 Token 註冊

App/Web 取得系統推播權限後,將自己的 push token(FCM/APNs registration token 或 Web Push
subscription)送到後端登記,綁定於目前登入的使用者帳號。使用者關閉通知權限或登出時,
前端呼叫解除登記。

**同一個端點只會有一筆登記**:唯一鍵是 `(platform, token)`,不含 `user_id`
(見 `01_資料模型與儲存規格.md` 第 2.6 節的唯一索引)。同一支手機換帳號登入時,
既有紀錄的 `user_id` **改綁為新登入者**,`id` 不變(審查 #4)。若不改綁,前一位使用者的
寵物活動會推到現在由他人使用的裝置上。

`PUT /push-tokens` 的回應**不含 token 本身**——token 等同可對該裝置發推播的憑證(審查 #10)。

### 2.5 Token 失效處理

發送時若推播服務回報該端點已失效(FCM `NotRegistered` / `Unregistered`、APNs `410`、
Web Push `404`/`410`),後端刪除該筆 `push_tokens` 紀錄並停止對它發送,不影響同一次通知
對其他端點的發送結果(對應 `PUSH_003`)。

## 3. API 介面

| Method | Path | 呼叫者 | 說明 |
|---|---|---|---|
| PUT | `/push-tokens` | App/Web | 註冊或更新目前裝置的 push token(附 platform:app/web);回 200 `{id, platform, created_at}` |
| GET | `/push-tokens` | App/Web | 列出本人已登記的端點(不含 token 明碼),供設定頁還原開關狀態(審查 #11) |
| DELETE | `/push-tokens/{push_token_id}` | App/Web | 解除登記(通知關閉或登出時呼叫) |
| POST | `/internal/notifications/event-ready` | **內部**(Event worker) | 事件轉 `ready` 後觸發推播,回 202(審查 #1) |

`/internal/*` 端點只走 VCN 私有網路、不經 Load Balancer,並以 `X-Internal-Api-Key`
標頭把關,與 Album 服務的內部端點同一套機制(見 `12_spec_相簿與雲端匯出.md` 第 3 節)。

**刪除帳號不需要本服務的端點**:`push_tokens` 的外鍵 `ON DELETE CASCADE` 會在 Auth 刪除
`users` 時一併帶走(見 `01_資料模型與儲存規格.md` 第 6 節)。內部清除端點只保留給「刪掉
資料列還不夠」的服務——Device 與 Album 必須另外刪 R2 物件,外鍵管不到物件儲存,
本服務沒有這類副作用。原審查 #8 的 `DELETE /internal/users/{user_id}/push-tokens` 因此取消。

`POST /internal/notifications/event-ready` 的 body:

```json
{
  "event_id": "uuid",
  "device_id": "uuid",
  "confidence_score": 0.92,
  "thumbnail_object_key": "thumbnails/{device_id}/2026/09/20/{event_id}.jpg",
  "started_at": "2026-09-20T03:14:00Z"
}
```

`DELETE /push-tokens/{push_token_id}`:**找不到與非本人一律回 404**,不回 403,
避免洩漏其他使用者的 token 是否存在(審查 #5)。

`PUT /push-tokens` 納入全站限流 `RATE_001`(App 每次啟動都會呼叫),每使用者每分鐘 10 次(審查 #16)。

## 4. 平台差異

| 項目 | 手機原生 App | Web |
|---|---|---|
| 推播機制 | FCM(Android)/APNs(iOS) | Web Push + Service Worker |
| 授權時機 | App 內首次啟動請求權限 | 使用者於瀏覽器主動同意 |

## 5. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 設定頁載入通知授權狀態 | 開關元件顯示 loading spinner,取得狀態後切換為實際開關值 |
| 使用者切換通知開關 | 開關本身 disable + spinner,完成後恢復可互動 |

開關的實際值 = 系統推播權限(OS 層,前端自行查詢)**且** `GET /push-tokens` 中有本裝置的登記。
前端不可只依賴本機儲存的 `push_token_id`,清除 storage 或換裝置後會與後端狀態不一致(審查 #11)。

## 6. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| PUSH_001 | - | 使用者拒絕通知權限 | 通知未開啟 | 設定頁顯示狀態 + 導引開啟按鈕 |
| PUSH_002 | - | 裝置 token 註冊失敗,前端背景重試中 | (不對使用者顯示) | - |
| PUSH_003 | - | Push token 失效 | (不對使用者顯示,刪除該筆並停止發送) | - |

三者都是**前端/後端內部的狀態標記,不是 API 回應碼**(審查 #9、#15):

- `PUSH_003` 原標示 HTTP 410,但 token 失效是推播服務(FCM/APNs)回報給後端的結果,
  本服務的任何端點都不會把 410 回給前端。處理方式見第 2.5 節。
- `PUSH_002` 原標示 HTTP 500。註冊失敗時後端實際回傳的是全域錯誤碼
  `SRV_001`/`SRV_002`(見 `10_錯誤處理與狀態規範.md` 第 3 節);`PUSH_002` 保留為前端
  「登記失敗、正在背景重試」的自有狀態,避免同一情境有兩個後端錯誤碼。

## 7. 驗收標準

- [ ] 事件 `status = ready` 後 10 秒內使用者手機收到通知
- [ ] 通知含縮圖且點擊後正確導向該事件播放頁
- [ ] 5 分鐘內連續 3 次觸發,只收到 1 次首發 + 1 次合併通知(第 3 次靜默)
- [ ] 拒絕通知權限後,App/Web 其餘功能不受影響,設定頁顯示 PUSH_001 狀態
- [ ] iOS(APNs)、Android(FCM)、桌面瀏覽器(Web Push)三種管道皆驗證送達
- [ ] 使用者授權通知後,push token 成功登記;關閉通知或登出後,token 被解除登記
- [ ] 同一支手機以 B 帳號登入後,A 帳號的事件不再推播到該裝置
- [ ] 已解除配對的裝置產生的事件不觸發任何推播

## 8. 規格審查決議(2026-09-20)

開發前審查的阻斷問題與決議,編號在測試 docstring 中可追溯:

| # | 問題 | 決議 |
|---|------|------|
| 1 | 沒有觸發推播的介面 | 新增 `POST /internal/notifications/event-ready`,Event worker 呼叫,回 202 背景送 |
| 2 | Push 拿不到裝置名稱與擁有者 | Push 呼叫 Device 服務 `GET /internal/devices/{device_id}` 取即時值 |
| 3 | 合併通知的送出時機未定義 | 第二個事件抵達時立即送一則「偵測到多次活動」,其餘靜默 |
| 4 | 契約寫 `(user_id, platform, token)`、DB 唯一索引是 `(platform, md5(token))` | 以 `(platform, token)` 為衝突鍵,換帳號時改綁 `user_id` |
| 5 | `PushTokenRepository` 缺 `get_by_id`,無法驗證擁有者(IDOR) | 新增 `get_by_id`;非本人與不存在一律 404 |
| 6 | 通知縮圖 presigned URL 效期 10 分鐘太短 | 通知用 30 分鐘,寫回資料模型第 3.3 節 |
| 7 | 「高信心/一般」門檻未定義 | `>= 0.8` 為高信心 |
| 8 | 刪除帳號的串聯清除沒有端點 | **不新增端點**:`push_tokens` 靠外鍵 `ON DELETE CASCADE` 隨 `users` 一併刪除。內部端點只留給另有 R2 物件要清的 Device 與 Album(見第 3 節) |
| 9 | `PUSH_003` 標 410 但無處可回 | 改為內部狀態標記,不對外回傳 |
| 10 | `PUT` 回應內容未定義 | 回 `{id, platform, created_at}`,不含 token |
| 11 | 設定頁無從查詢登記狀態 | 新增 `GET /push-tokens` |
| 12 | ADR 只寫了發送路徑的降級 | 註冊/刪除(寫入 Postgres)選 C 回 `SRV_002`;發送查詢選 A 重試。寫回 ADR 第 4 節 |
| 13 | 事件觸發時裝置可能已無擁有者 | 直接捨棄,不推播不報錯 |
| 14 | 合併通知的 deep link 未定義 | 導向該裝置的攝影機畫面 |
| 15 | `PUSH_002` 與 `SRV_001` 語意重疊 | `PUSH_002` 保留為前端自有狀態 |
| 16 | `PUT /push-tokens` 未納入限流 | 每使用者每分鐘 10 次 |
