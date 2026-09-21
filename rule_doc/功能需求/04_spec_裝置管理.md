# 功能規格書:裝置管理(F0.3)

| 項目 | 內容 |
|---|---|
| 優先級 | P0 |
| 相依功能 | F0.2(裝置需已配對) |
| 資料模型 | `01_資料模型與儲存規格.md` — `devices` 表、第 6 節刪除串聯規則 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |

## 1. 使用者故事

1. 作為使用者,我想看到我所有已配對的鏡頭列表與線上狀態。
2. 作為使用者,我想幫鏡頭重新命名,方便辨識多個房間。
3. 作為使用者,我想移除不再使用的鏡頭。

## 2. 功能說明

### 2.1 裝置列表

顯示使用者名下所有裝置,包含名稱與線上/離線狀態(狀態來源見 `03_spec_裝置配對.md` 第 2.3 節心跳機制)。

### 2.2 重新命名

使用者於裝置列表或裝置詳情頁修改 `name` 欄位,即時儲存。

### 2.3 移除裝置

破壞性操作,需二次確認對話框。確認後依 `01_資料模型與儲存規格.md` 第 6 節,刪除該裝置所有事件紀錄與 R2 影片/縮圖,裝置狀態重置為 `pending` 並清空 `user_id`。

事件紀錄與 R2 物件的刪除由本服務呼叫 Event 服務的內部端點
`DELETE /internal/devices/{device_id}/events` 完成(見 `08_spec_時間軸與事件歷史.md`
第 3.3 節):`events` 表屬於 Event 服務,R2 key 也需要 `event_id` 才組得出來。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| GET | `/devices` | 取得使用者已配對的裝置列表 |
| PATCH | `/devices/{device_id}` | 重新命名裝置 |
| DELETE | `/devices/{device_id}` | 移除裝置(連同事件與影片一併刪除) |
| GET | `/internal/devices/{device_id}` | **內部**:供 Event、Push 等服務取得裝置擁有者與名稱 |

`/devices/{device_id}/events` 不屬於本服務,由 **Event 服務**提供,Load Balancer 的分流
規則見 `08_spec_時間軸與事件歷史.md` 第 3.1 節。

`GET /internal/devices/{device_id}` 以 `X-Internal-Api-Key` 把關,回傳該裝置的 `id`、
`name`、`user_id` 與 `status`,供其他服務做擁有者驗證與顯示(`events` 沒有 `user_id`,
Event 服務必須問 Device 才知道某個裝置是誰的,見 `08_spec_時間軸與事件歷史.md` 第 3.2 節;
Push 服務另外需要 `name` 組通知標題,見 `09_spec_推播通知.md` 第 2.1 節)。
不回傳 `pairing_code` 等配對憑證。`user_id` 為 `null` 代表裝置未配對或已解除配對,
呼叫端據此自行決定行為(Event 回 404、Push 捨棄通知)。
| DELETE | `/internal/users/{user_id}/devices` | **內部**:Auth 服務刪除帳號時串聯清除該帳號名下所有裝置,見 `01_資料模型與儲存規格.md` 第 6 節 |

`DELETE /internal/users/{user_id}/devices` 對該帳號名下每一台裝置執行與 `DELETE /devices/{device_id}` 相同的移除邏輯(刪除該裝置的 `events` 與對應 R2 物件、`devices` 重置為 `pending` 並清空 `user_id`),名下沒有裝置時視為成功。此端點必須**冪等**:Auth 重試時重複呼叫不得失敗。內部端點只走 VCN 私有網路、不經 Load Balancer(見 `13_ADR_微服務與三節點部署.md` 第 1 節),另以共享金鑰標頭 `X-Internal-Api-Key` 把關。

## 4. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 裝置列表載入 | skeleton 列表項 |
| 重新命名送出後 | 欄位旁小型 spinner,完成後即時顯示新名稱 |
| 移除裝置確認後 | 對話框內確認按鈕 disable + spinner,完成後導向裝置列表並移除該卡片 |

## 5. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| DEVICE_004 | - | 心跳逾時 | (裝置列表狀態顯示離線,非跳出錯誤) | 列表項狀態標示 |
| DEVICE_005 | 404 | 裝置不存在或已被移除 | 找不到此裝置 | 導回裝置列表 + Toast |

## 6. 驗收標準

- [ ] 裝置列表正確顯示線上/離線狀態
- [ ] 使用者可重新命名裝置,列表即時反映新名稱
- [ ] 使用者移除裝置需二次確認,確認後該裝置與其所有事件、影片一併從系統移除
- [ ] 對已不存在的裝置操作(如另一分頁已移除)顯示 DEVICE_005
