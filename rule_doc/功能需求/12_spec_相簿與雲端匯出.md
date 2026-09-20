# 功能規格書:相簿與 Google Drive 匯出(F6)

| 項目 | 內容 |
|---|---|
| 優先級 | P1 |
| 相依功能 | F5(剪輯與截圖,相簿內容來源) |
| 資料模型 | `01_資料模型與儲存規格.md` — `media_items` 表、相簿項目狀態機 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |

## 1. 使用者故事

1. 作為使用者,我想瀏覽保存下來的照片與剪輯,依日期分類。
2. 作為使用者,我想把相簿內容匯出備份到自己的 Google Drive。

## 2. 功能說明

### 2.1 相簿瀏覽

依 `captured_at` 日期由新到舊分組,每組以日期作為大 Title(如「2026年9月」),組內以縮圖網格顯示。

列表回傳 `processing` / `ready` / `failed` 三種狀態的項目,由前端依狀態決定呈現方式(見 `11_spec_剪輯與截圖.md` 第 4 節:`processing` 顯示 spinner +「處理中」、`failed` 顯示錯誤圖示)。**只有 `ready` 的項目可以播放與匯出**;非 `ready` 的項目不提供內容連結。

分頁採 `(captured_at, id)` 組合游標,不用 offset:相簿會持續有新項目寫入,offset 分頁會讓使用者往下捲時重複或漏掉項目;同一秒保存的多個項目再以 `id` 決勝。游標為不透明字串,由後端產生,前端原樣回傳。

日期篩選有兩種,互斥:`date=YYYY-MM-DD` 取單日(App 版用),`from`/`to` 取區間且**起訖日均含**(Web 版左側「最近 7 天 / 最近 30 天 / 自訂範圍」篩選欄用)。兩者同時指定或格式不符回 `VAL_001`;空字串視為未指定(前端清空篩選欄時送出的是 `?date=`)。

**分組與篩選的時區固定為台北時間(`Asia/Taipei`)。** `captured_at` 本身仍以 UTC 儲存(`01_資料模型與儲存規格.md` 第 2.0 節),只在判斷「屬於哪一天」時換算成台北時間。這一點必須明確,否則台北時間凌晨 1 點拍的照片(UTC 仍是前一天 17:00)會被歸到前一天的分組,使用者會看到日期跑掉。目前系統只服務單一時區的使用者,不依使用者所在地動態調整;未來若要支援跨時區,改的是這一個設定值。

### 2.2 刪除相簿項目

使用者可手動刪除單一 `media_items` 紀錄,連同對應 R2 物件一併刪除。破壞性操作,需二次確認。

### 2.3 Google Drive 匯出

1. 使用者於相簿選擇一個或多個項目,點擊「匯出到 Google Drive」。
2. 若尚未連結 Google 帳號,先導向 Google OAuth 授權頁,僅申請 `drive.file` scope(僅能存取本 App 建立的檔案,不要求存取使用者既有雲端硬碟內容)。
3. 授權完成後,後端非同步將檔案上傳至使用者 Google Drive 內固定資料夾(「寵物攝影機」),`drive_export_status` 依序更新為 `exporting` → `exported` 或 `failed`。
4. 同一項目可重複匯出(如授權變更後);已 `exported` 的項目仍可再次觸發匯出。

補充規則:

- 單次匯出上限 **50** 個項目;超過回 `VAL_001`。
- 已處於 `exporting` 的項目**跳過不重送**,避免在 Drive 產生重複檔案;回應中以 `skipped_ids` 告知前端。
- 僅 `status = ready` 的項目可匯出,其餘回 `VAL_001`。
- `exporting` 停留超過 **15 分鐘**由後端改判為 `failed`(`DRIVE_002`),確保狀態機有終止保證——匯出是背景工作,服務複本重啟後進行中的任務會消失。
- 取得授權連結時產生一次性 `state` 並綁定當前使用者(存於共用 Redis,TTL 10 分鐘),回呼時驗證,防 CSRF。**此處 Redis 不可用時 fail-closed 回 `SRV_002`**,與全站限流的 fail-open 取捨不同(見 `13_ADR_微服務與三節點部署.md` 第 4 節)。
- 匯出中的項目仍可刪除;背景任務發現紀錄已不存在即中止。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| GET | `/media?date=&from=&to=&cursor=&limit=` | 取得相簿項目(依日期分組、分頁) |
| DELETE | `/media/{media_item_id}` | 刪除相簿項目 |
| GET | `/integrations/google-drive/oauth-url` | 取得 Google OAuth 授權連結 |
| POST | `/integrations/google-drive/oauth-callback` | OAuth 回呼,完成授權綁定 |
| POST | `/media/export/google-drive` | 送出匯出請求(附項目 id 清單),回 `202` 表示已受理 |
| DELETE | `/internal/users/{user_id}/media` | **內部**:Auth 服務刪除帳號時串聯清除,見 `01_資料模型與儲存規格.md` 第 6 節 |

**路由邊界**:`GET /media/{media_item_id}`(單筆內容查詢)屬於 Media 服務(`11_spec_剪輯與截圖.md` 第 3 節),不由本服務提供。Load Balancer 依此分流:`GET /media`、`DELETE /media/{id}`、`POST /media/export/google-drive` → Album;`GET /media/{id}` → Media。

`GET /media` 的回應為每個項目夾帶效期 10 分鐘的 presigned URL(內容與縮圖各一,見 `01_資料模型與儲存規格.md` 第 3.3 節),不外洩 R2 object key。相簿網格一次顯示數十個項目,逐一向 Media 服務換取連結不切實際。

內部端點只走 VCN 私有網路、不經 Load Balancer(見 `13_ADR_微服務與三節點部署.md` 第 1 節),另以共享金鑰標頭把關。

## 4. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 首次載入相簿 | 依日期分組的 skeleton 網格 |
| 捲動載入更多 | 底部小型 spinner |
| 點擊「匯出到 Google Drive」且尚未授權 | 導向 Google 授權頁,期間顯示 spinner 遮罩 |
| 匯出處理中 | 對應項目縮圖疊加「匯出中」圖示,不阻塞其他相簿操作 |
| 匯出完成 | Toast 提示「已匯出至 Google Drive」 |
| 刪除項目確認後 | 對話框確認按鈕 disable + spinner,完成後從網格移除該項目 |

## 5. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| DRIVE_001 | 401 | 尚未連結 Google Drive 或授權已失效 | 請重新連結 Google 帳號 | 阻斷式,導向 OAuth 授權頁 |
| DRIVE_002 | - | 匯出失敗(如 Google Drive 額度不足) | 匯出失敗,請稍後再試 | 對應項目縮圖顯示錯誤圖示 + Toast |
| DRIVE_003 | 401 | OAuth 授權過期 | 授權已過期,請重新連結 | 阻斷式,導向 OAuth 授權頁 |

## 6. 驗收標準

- [ ] 相簿依日期分組正確顯示,新到舊排序
- [ ] 使用者可刪除相簿項目,刪除後對應 R2 物件一併移除
- [ ] 首次匯出時導向 Google OAuth 授權,僅申請 `drive.file` scope
- [ ] 授權完成後,選取項目可成功上傳至 Google Drive 指定資料夾
- [ ] 匯出失敗時顯示 DRIVE_002,不影響該項目在相簿內的正常瀏覽
- [ ] 授權過期後再次匯出顯示 DRIVE_003 並導向重新授權
