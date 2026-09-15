# 功能規格書:登入註冊與密碼重設(F0.1)

| 項目 | 內容 |
|---|---|
| 優先級 | P0 |
| 資料模型 | `01_資料模型與儲存規格.md` — `users` 表、`refresh_tokens` 表、`oauth_identities` 表 |
| 共用規範 | `10_錯誤處理與狀態規範.md` |

## 1. 使用者故事

1. 作為新使用者,我想註冊帳號。
2. 作為使用者,我想用 email/密碼登入。
3. 作為使用者,我想用 Google 或 Apple 帳號直接登入,不需另外設定密碼。
4. 作為使用者,我忘記密碼時想透過 email 重設密碼。
5. 作為使用者,我想在 Web 上登出。

## 2. 功能說明

### 2.1 帳號欄位與密碼規則

以下規則套用於本文件涵蓋的所有表單(登入、註冊、忘記密碼、重設密碼),前端於欄位失焦或送出時即時驗證,不符合時顯示對應提示且不呼叫後端 API;後端亦重複驗證,不符合時回傳對應錯誤碼。

| 欄位 | 規則 | 前端即時驗證訊息 | 對應錯誤碼 |
|---|---|---|---|
| Email | 必填 | 「請輸入 Email」 | `VAL_001` |
| Email | 需符合 Email 格式(`本地部分@網域`),長度上限 254 字元 | 「Email 格式不正確」 | `VAL_001` |
| 密碼 | 必填 | 「請輸入密碼」 | `VAL_001` |
| 密碼 | 至少 8 碼、至多 72 碼(bcrypt 雜湊上限),需包含至少一個英文字母與一個數字,允許任意可列印 ASCII 字元 | 「密碼需至少 8 碼,並包含英文字母與數字」 | `AUTH_006`(見第 5 節) |
| 確認新密碼(重設密碼頁) | 必填,且需與新密碼欄位完全一致 | 「兩次輸入的密碼不一致」 | `VAL_001` |

密碼規則套用於註冊、忘記密碼重設、`05_spec_帳號設定.md` 的修改密碼。`VAL_001` 定義於 `10_錯誤處理與狀態規範.md` 第 3 節,呈現方式為 Inline 於對應欄位下方。

### 2.2 註冊

Email + 密碼建立帳號,密碼雜湊儲存(bcrypt/argon2)。Email 需唯一,欄位規則見 2.1 節。

### 2.3 登入

Email + 密碼登入,登入請求需附帶 `platform` 參數(`app` / `web`),後端依平台簽發不同的 token 機制:

- **Web**:簽發 access token(JWT,有效期 1 小時)+ refresh token(有效期 30 天,雜湊後存入 `refresh_tokens` 表,可撤銷)。
- **App**:僅簽發單一 access token(JWT,有效期 180 天),不使用 refresh token,靠 2.3.2 的滑動展延機制維持長期登入。

連續 5 次登入失敗鎖定帳號 15 分鐘(不分平台,以帳號為單位計算)。此鎖定計數僅計算 `/auth/login`(email/密碼登入)的失敗次數,不含 2.7 節第三方登入。

#### 2.3.1 Web:Access Token + Refresh Token

- Access token 到期後,前端呼叫 `/auth/token/refresh` 並附上 refresh token 換發新的 access token,不需使用者重新輸入密碼。
- 每次換發時採用 **rotation**:舊 refresh token 立即失效,同時發出一組新的 refresh token,防止外洩的 refresh token 被重複使用。
- 使用者登出時,後端將該 refresh token 標記撤銷(`revoked_at`),之後即使前端還留著舊 token 也無法再換發 access token。

#### 2.3.2 App:Token 滑動展延(Sliding Expiration)

- App 每次呼叫任一已登入 API 時,若目前 token 核發已超過 7 天,後端於回應中夾帶重新簽發、效期再延 180 天的新 token,App 端靜默更新本機儲存的 token。
- 只要使用者至少每 180 天開啟一次 App(觸發一次 API 呼叫),token 就會持續展延,近似「長期保持登入」。
- 若連續 180 天完全未使用 App(未觸發任何展延),token 到期後需重新輸入帳密登入。

### 2.4 忘記密碼

1. 使用者於登入頁點擊「忘記密碼」,輸入 email。
2. 後端產生一次性重設 token(有效期 30 分鐘),寄送重設連結至該 email。**不論該 email 是否已註冊,一律回傳相同成功訊息**,避免帳號列舉。
3. 使用者點擊信件連結進入重設密碼頁,輸入新密碼與確認新密碼,欄位規則見 2.1 節。
4. 後端驗證 token 有效且未使用、未過期,更新 `password_hash`,並使該 token 立即失效。
5. 重設成功後導回登入頁,不自動登入。

### 2.5 登出

**僅 Web 提供登出功能**:前端呼叫後端撤銷目前的 refresh token(`revoked_at` 標記),並清除本機 access token 與 refresh token,導向登入頁。撤銷後即使 access token 尚未到期,一旦過期就無法再換發新的。

**App 不提供登出功能**:App 定位為長期保持登入的裝置端應用,UI 上不顯示登出選項。使用者若要脫離登入狀態,只能透過解除安裝 App 或清除本機資料,token 自然失效(過期後需重新登入)。

### 2.6 平台差異

| 項目 | 手機原生 App | Web |
|---|---|---|
| Token 機制 | 單一 access token,滑動展延 | access token + refresh token |
| Access token 有效期 | 180 天(每次使用超過 7 天自動展延) | 1 小時 |
| Refresh token 有效期 | 不適用 | 30 天,每次使用 rotation |
| 登出功能 | 不提供 | 提供(撤銷 refresh token + 清除本機 token) |
| 登入請求 `platform` 參數 | `app` | `web` |

第三方登入(2.7 節)不受此表影響:App、Web 皆提供相同的 Google/Apple 登入選項,登入成功後依上表各自的 token 機制簽發,差異僅在於前端取得 provider id_token 的方式(App 使用原生 SDK,Web 使用 provider 的 JS SDK)。

### 2.7 第三方登入(OAuth)

支援 Google、Apple 兩種 provider,App 與 Web 皆提供,行為與帳密登入完全共用同一組 token 簽發機制(2.3、2.3.1、2.3.2 節)。

1. 前端取得 provider 簽發的 id_token:App 使用 Google Sign-In / Sign in with Apple 原生 SDK;Web 使用 Google Identity Services JS SDK / Sign in with Apple JS,取得後呼叫 `/auth/oauth/login`,附帶 `provider`(`google`/`apple`)、`id_token`、`platform`。
2. 後端向 provider 驗證 id_token 簽章、有效期、`aud` 是否為本專案已註冊的 client ID,驗證失敗回傳 `AUTH_011`。
3. 驗證成功後依 `(provider, provider_user_id)` 查詢 `oauth_identities`:
   - 已存在對應紀錄:視為登入既有帳號。
   - 不存在,但 id_token 內的 email 與既有 `users.email` 相符:**自動綁定**,建立 `oauth_identities` 紀錄並關聯至該既有帳號,視為登入該帳號(因 provider 已驗證 email 所有權,無需使用者再次確認)。
   - Email 亦不存在:視為新使用者,建立 `users` 紀錄(`password_hash` 為 `null`)與對應 `oauth_identities` 紀錄,直接登入(註冊與登入合併為單一步驟)。
4. 登入成功後依 2.3 節 `platform` 參數簽發對應 token,與帳密登入共用同一套機制,無額外差異。
5. 僅透過第三方登入建立、尚未設定密碼(`password_hash` 為 `null`)的帳號,仍可透過 2.4 節「忘記密碼」流程設定密碼,藉此之後也能改用 email/密碼登入;該帳號的忘記密碼流程與一般帳號完全相同,不額外區分。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| POST | `/auth/register` | 註冊帳號 |
| POST | `/auth/login` | 登入,依 `platform` 參數簽發對應 token |
| POST | `/auth/oauth/login` | 第三方登入(Google/Apple),驗證 provider id_token 後依 `platform` 參數簽發對應 token,見 2.7 節 |
| POST | `/auth/token/refresh` | Web 專用:用 refresh token 換發新的 access token(rotation) |
| POST | `/auth/logout` | Web 專用:撤銷目前 refresh token |
| POST | `/auth/password/forgot` | 送出忘記密碼請求(輸入 email) |
| POST | `/auth/password/reset` | 使用重設 token 設定新密碼 |

## 4. 讀取狀態

| 階段 | UI 呈現 |
|---|---|
| 註冊/登入按鈕點擊後 | 按鈕 disable + spinner |
| 第三方登入按鈕點擊後 | 按鈕 disable + spinner,等待 provider 互動完成與後端驗證 |
| 忘記密碼送出後 | 按鈕 disable + spinner,完成後顯示「若該 Email 存在,重設連結已寄出」 |
| 重設密碼頁載入(驗證連結) | 進頁面時先驗證 token,顯示 spinner;token 無效顯示全頁錯誤 |
| 重設密碼送出後 | 按鈕 disable + spinner |

## 5. 錯誤碼

| 錯誤碼 | HTTP Status | 說明 | 使用者訊息 | 呈現方式 |
|---|---|---|---|---|
| AUTH_003 | 401 | 登入帳密錯誤 | 帳號或密碼錯誤 | Inline 於登入表單 |
| AUTH_004 | 409 | 註冊 Email 已存在 | 此 Email 已被註冊 | Inline 於註冊表單 |
| AUTH_005 | 423 | 連續登入失敗過多,帳號暫時鎖定 | 登入失敗次數過多,請 15 分鐘後再試 | 阻斷式對話框 + 倒數時間 |
| AUTH_006 | 400 | 密碼不符強度規則 | 密碼需至少 8 碼,並包含英文字母與數字 | Inline 於密碼欄位 |
| AUTH_007 | 410 | 密碼重設連結無效或已過期 | 此連結已失效,請重新申請 | 全頁錯誤 + 「重新申請」按鈕 |
| AUTH_010 | 401 | Web refresh token 無效、已撤銷或已過期 | 登入已逾時,請重新登入 | 阻斷式,導向登入頁 |
| AUTH_011 | 401 | 第三方登入 id_token 驗證失敗、已過期或 `aud` 不符 | 第三方登入驗證失敗,請重新嘗試 | Inline 於登入表單 |

Email 必填/格式錯誤、密碼必填、確認新密碼不一致等欄位驗證錯誤沿用全域 `VAL_001`(定義於 `10_錯誤處理與狀態規範.md` 第 3 節),各欄位對應訊息見第 2.1 節,本文件不重複列出。

## 6. 驗收標準

- [ ] 使用者可完成註冊、登入
- [ ] Email 欄位空白或格式不正確時顯示 VAL_001 對應訊息,無法送出
- [ ] 密碼不符規則時顯示 AUTH_006,無法送出
- [ ] 重設密碼頁「確認新密碼」與新密碼不一致時顯示 VAL_001 對應訊息,無法送出
- [ ] 連續登入失敗 5 次後顯示 AUTH_005 並鎖定 15 分鐘
- [ ] 忘記密碼流程中,無論 email 是否存在都顯示相同成功訊息
- [ ] 重設連結 30 分鐘後失效,過期點擊顯示 AUTH_007
- [ ] 重設密碼成功後舊密碼失效,須用新密碼重新登入
- [ ] Web 登入取得 access token(1 小時)與 refresh token(30 天)
- [ ] App 登入取得單一 access token,有效期 180 天
- [ ] Web access token 過期後,可用 refresh token 靜默換發新 access token,不需重新輸入密碼
- [ ] Web 每次換發 refresh token 皆 rotation,舊 refresh token 立即失效
- [ ] Web 登出後,原 refresh token 無法再換發新 access token(顯示 AUTH_010)
- [ ] App 每次使用超過 7 天自動展延 token 效期;連續 180 天未使用則過期需重新登入
- [ ] App 平台 UI 上不提供登出選項
- [ ] 使用者可用 Google 或 Apple 帳號登入,首次登入自動建立帳號(無需另外填寫註冊表單)
- [ ] 第三方登入 email 與既有帳號相符時自動綁定並登入該帳號,不需使用者額外確認
- [ ] 第三方登入 id_token 驗證失敗時顯示 AUTH_011
- [ ] 僅透過第三方登入建立的帳號,`password_hash` 為 null,仍可透過忘記密碼流程設定密碼
- [ ] 第三方登入失敗不計入 AUTH_005 的登入失敗鎖定次數
