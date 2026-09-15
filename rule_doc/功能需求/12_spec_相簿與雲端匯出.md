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

依 `captured_at` 日期由新到舊分組,每組以日期作為大 Title(如「2026年9月」),組內以縮圖網格顯示。僅列出 `status = ready` 的項目。

### 2.2 刪除相簿項目

使用者可手動刪除單一 `media_items` 紀錄,連同對應 R2 物件一併刪除。破壞性操作,需二次確認。

### 2.3 Google Drive 匯出

1. 使用者於相簿選擇一個或多個項目,點擊「匯出到 Google Drive」。
2. 若尚未連結 Google 帳號,先導向 Google OAuth 授權頁,僅申請 `drive.file` scope(僅能存取本 App 建立的檔案,不要求存取使用者既有雲端硬碟內容)。
3. 授權完成後,後端非同步將檔案上傳至使用者 Google Drive 內固定資料夾(「寵物攝影機」),`drive_export_status` 依序更新為 `exporting` → `exported` 或 `failed`。
4. 同一項目可重複匯出(如授權變更後);已 `exported` 的項目仍可再次觸發匯出。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| GET | `/media?date=&cursor=&limit=` | 取得相簿項目(依日期分組、分頁) |
| DELETE | `/media/{media_item_id}` | 刪除相簿項目 |
| GET | `/integrations/google-drive/oauth-url` | 取得 Google OAuth 授權連結 |
| POST | `/integrations/google-drive/oauth-callback` | OAuth 回呼,完成授權綁定 |
| POST | `/media/export/google-drive` | 送出匯出請求(附項目 id 清單) |

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
