# 功能規格書:登入註冊與密碼重設(F0.1)

| 項目 | 內容 |
|---|---|
| 優先級 | P0 |
| 資料模型 | `01_資料模型與儲存規格.md` — `users` 表、`refresh_tokens` 表、`oauth_identities` 表、`password_reset_tokens` 表 |
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

**Email 正規化**:所有接受 email 的端點(註冊、登入、忘記密碼、刪除帳號的 Email 確認)後端一律先去除頭尾空白並轉為小寫,再進行比對與寫入。`users.email` 有 `CHECK email = lower(email)` 約束(見 `01_資料模型與儲存規格.md` 第 2.1 節),不先正規化會讓 `A@x.com` 這類輸入撞上資料庫約束而回 `SRV_001`,而不是預期的 `AUTH_004`。正規化屬於後端責任,前端不需處理。

**密碼長度以位元組計**:「至多 72 碼」是 bcrypt 的 72 **bytes** 上限。規格限定密碼只允許可列印 ASCII(U+0020~U+007E),此時字元數等於位元組數;輸入含非 ASCII 字元(中文、emoji)或超過 72 bytes 時回 `AUTH_006`,前端提示訊息為「密碼只能使用英數字與常見符號,長度 8~72 碼」。

### 2.2 註冊

Email + 密碼建立帳號,密碼雜湊儲存(bcrypt/argon2)。Email 需唯一,欄位規則見 2.1 節。

唯一性由 `users.email` 的唯一約束保證,不以「先查詢再寫入」判斷:兩個同 email 的註冊請求同時進來時,先查後寫會雙雙查到「不存在」而都嘗試寫入。後端捕捉唯一約束違反並轉為 `AUTH_004`,與先查到既有帳號時的回應完全相同。

### 2.3 登入

Email + 密碼登入,登入請求需附帶 `platform` 參數(`app` / `web`),後端依平台簽發不同的 token 機制:

- **Web**:簽發 access token(JWT,有效期 1 小時)+ refresh token(有效期 30 天,雜湊後存入 `refresh_tokens` 表,可撤銷)。
- **App**:僅簽發單一 access token(JWT,有效期 180 天),不使用 refresh token,靠 2.3.2 的滑動展延機制維持長期登入。

連續 5 次登入失敗鎖定帳號 15 分鐘(不分平台,以帳號為單位計算)。此鎖定計數僅計算 `/auth/login`(email/密碼登入)的失敗次數,不含 2.7 節第三方登入。

- **計數儲存**:`users.failed_login_attempts` 與 `users.locked_until` 兩欄(見 `01_資料模型與儲存規格.md` 第 2.1 節)。登入成功、或鎖定期滿後的第一次登入嘗試,計數歸零。
- **計數鍵為送入的 email 字串,不論該帳號是否存在**。若只對存在的帳號鎖定(存在回 `AUTH_005`、不存在回 `AUTH_003`),攻擊者只要送 5 次錯誤密碼就能判斷任一 email 有沒有註冊,這與 2.4 節刻意避免帳號列舉的設計互相抵觸。因此不存在的 email 連續失敗 5 次同樣回 `AUTH_005`,計數以 Redis 鍵 `login:fail:{email}`(TTL 15 分鐘)承接;存在的帳號則以 `users` 的兩個欄位為準。兩者回應完全相同,呼叫端無法區分。
- **鎖定期間**:即使密碼正確也一律回 `AUTH_005`,不得放行,也不重置計數。
- **回應**:`AUTH_005` 的回應 body 帶 `retry_after_seconds`(整數秒),供前端顯示第 5 節要求的倒數時間。
- **Redis 不可用時**:對不存在帳號的計數降級為不鎖定(fail-open,與 `10_錯誤處理與狀態規範.md` 的限流一致);已存在帳號的鎖定仍然生效,因為它存在 Postgres,而 Postgres 不可用時 Auth 一律回 `SRV_002`(見 `13_ADR_微服務與三節點部署.md` 第 4 節)。

#### 2.3.1 Web:Access Token + Refresh Token

- Access token 到期後,前端呼叫 `/auth/token/refresh` 並附上 refresh token 換發新的 access token,不需使用者重新輸入密碼。
- 每次換發時採用 **rotation**:舊 refresh token 立即失效,同時發出一組新的 refresh token,防止外洩的 refresh token 被重複使用。
- 使用者登出時,後端將該 refresh token 標記撤銷(`revoked_at`),之後即使前端還留著舊 token 也無法再換發 access token。
- **重放偵測**:若收到的 refresh token 存在但**已被撤銷**,視為該 token 已外洩(正常用戶端不會重複使用已換發過的 token),後端撤銷該使用者**所有**未撤銷的 refresh token,再回 `AUTH_010`,強制所有 Web session 重新登入。查無此 token 則單純回 `AUTH_010`,不做連帶撤銷。
- **併發**:同一個 refresh token 的兩個換發請求同時到達時,撤銷動作以 `UPDATE refresh_tokens SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL` 的影響列數決定勝負——影響 0 列者視為重放,套用上一條規則。不得出現「一個 refresh token 換出兩組有效 token」。

#### 2.3.2 App:Token 滑動展延(Sliding Expiration)

- 展延由 **Auth 服務專責**,透過 `POST /auth/token/extend` 提供:App 帶現有的 access token 呼叫,後端驗證通過且該 token 的 `iat` 已超過 7 天時,重新簽發一組效期再延 180 天的新 token 回傳,App 端靜默更新本機儲存的 token;未滿 7 天則回傳 `204`,App 沿用原 token。
- App 在啟動時、以及每次收到 `204` 之外的回應後檢查本機 token 的 `iat`,滿 7 天才呼叫本端點,不是每支 API 都呼叫。
- **簽發能力只存在於 Auth 服務**:其餘六個服務只用共用密鑰**驗證** access token,不簽發也不換發。原先「每次呼叫任一已登入 API 時由後端夾帶新 token」的寫法,等於要求七個服務都具備簽發能力、共用簽章私鑰,token 生命週期規則也會散落在七份程式碼裡;改由 Auth 單點簽發後,`02_spec` 的效期規則只有一個實作位置。
- 只要使用者至少每 180 天開啟一次 App(觸發一次展延檢查),token 就會持續展延,近似「長期保持登入」。
- 若連續 180 天完全未使用 App(未觸發任何展延),token 到期後需重新輸入帳密登入。

### 2.4 忘記密碼

1. 使用者於登入頁點擊「忘記密碼」,輸入 email。
2. 後端產生一次性重設 token(有效期 30 分鐘),寄送重設連結至該 email。**不論該 email 是否已註冊,一律回傳相同成功訊息**,避免帳號列舉。
3. 使用者點擊信件連結進入重設密碼頁,輸入新密碼與確認新密碼,欄位規則見 2.1 節。
4. 後端驗證 token 有效且未使用、未過期,更新 `password_hash`,並使該 token 立即失效。
5. 重設成功後導回登入頁,不自動登入。同時撤銷該帳號所有未撤銷的 `refresh_tokens`:能重設密碼的人未必是原本持有既有 session 的人,不撤銷等於帳號被盜後改了密碼仍趕不走對方。

**Token 儲存**:重設 token 為密碼學亂數(至少 256 bits),明碼只出現在寄出的連結中,資料庫只存雜湊值,寫入 `password_reset_tokens` 表(見 `01_資料模型與儲存規格.md` 第 2.9 節)。驗證時以雜湊比對,並檢查 `used_at is null` 且 `expires_at > now()`;步驟 4 的「立即失效」即寫入 `used_at`。同一帳號重複申請時舊 token 不主動失效,各自依 30 分鐘期限自然過期。

**限流**:本端點以 `email` 與來源 IP 兩個維度各限 5 次/小時,超過回 `RATE_001`(定義於 `10_錯誤處理與狀態規範.md` 第 3 節)。全站預設限流(120 次/分鐘)對「會觸發寄信到第三人信箱」的端點太寬鬆,不足以防止拿本端點轟炸他人信箱。限流計數用共用 Redis(`ratelimit:{key}:{endpoint}`),Redis 不可用時依該文件規定 fail-open。

**寄信失敗**:寄信管道以 port 介面定義,實作由部署環境決定(本規格不指定 SMTP 服務商)。寄送失敗只記錄 log 並告警,對外仍回傳與成功完全相同的回應——回傳錯誤會讓呼叫端得知「這個 email 存在且系統嘗試寄信了」,破壞本節的反列舉設計。

### 2.5 登出

**僅 Web 提供登出功能**:前端呼叫後端撤銷目前的 refresh token(`revoked_at` 標記),並清除本機 access token 與 refresh token,導向登入頁。請求 body 帶 `refresh_token`(明碼,後端雜湊後比對);access token 可能已過期,因此本端點不要求 access token 有效。撤銷為**冪等**:查無此 token、或該 token 已撤銷、已過期,一律回 `204`,不回錯誤——登出失敗對使用者沒有可執行的復原動作,且回錯誤會洩漏 token 是否存在。本端點不套用 2.3.1 節的重放偵測。撤銷後即使 access token 尚未到期,一旦過期就無法再換發新的。

**App 不提供登出功能**:App 定位為長期保持登入的裝置端應用,UI 上不顯示登出選項。使用者若要脫離登入狀態,只能透過解除安裝 App 或清除本機資料,token 自然失效(過期後需重新登入)。

### 2.6 平台差異

| 項目 | 手機原生 App | Web |
|---|---|---|
| Token 機制 | 單一 access token,滑動展延 | access token + refresh token |
| Access token 有效期 | 180 天(核發滿 7 天後由 `POST /auth/token/extend` 展延) | 1 小時 |
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
   - 不存在,但 id_token 內的 email **已經 provider 驗證**(`email_verified` 為真)且與既有 `users.email` 相符:**自動綁定**,建立 `oauth_identities` 紀錄並關聯至該既有帳號,視為登入該帳號(因 provider 已驗證 email 所有權,無需使用者再次確認)。
   - id_token 未帶 `email_verified`、或其值不為真時,**不得自動綁定**,一律回 `AUTH_011`。這是帳號接管的防線:provider 端可以註冊一個未經驗證的 email,若僅憑 email 字串相符就綁定既有帳號,等於任何人都能拿走他人帳號。Apple 的 `email_verified` claim 型別可能是布林 `true` 或字串 `"true"`,兩者都視為真,其餘值(含缺漏)一律視為未驗證。
   - Email 亦不存在:視為新使用者,建立 `users` 紀錄(`password_hash` 為 `null`)與對應 `oauth_identities` 紀錄,直接登入(註冊與登入合併為單一步驟)。
4. 登入成功後依 2.3 節 `platform` 參數簽發對應 token,與帳密登入共用同一套機制,無額外差異。
5. 僅透過第三方登入建立、尚未設定密碼(`password_hash` 為 `null`)的帳號,仍可透過 2.4 節「忘記密碼」流程設定密碼,藉此之後也能改用 email/密碼登入;該帳號的忘記密碼流程與一般帳號完全相同,不額外區分。

### 2.8 Access token 的 claim 格式

Access token 為 JWT,以 HS256 與共用密鑰簽章,由 Auth 服務簽發,其餘六個服務只驗證。claim 如下:

| claim | 說明 |
|---|---|
| `sub` | `users.id`(uuid 字串) |
| `iat` | 簽發時間(Unix 秒),2.3.2 節判斷「核發是否已超過 7 天」的依據 |
| `exp` | 到期時間(Unix 秒),Web 為 `iat + 1 小時`、App 為 `iat + 180 天` |
| `platform` | `app` / `web`,供服務端判斷平台差異 |

驗證端一律明確指定演算法清單(擋掉 `alg=none` 與演算法混淆攻擊),並要求 `sub`、`exp`、`iat` 三個 claim 存在;缺漏或簽章不符回 `AUTH_001`,已過期回 `AUTH_002`(定義於 `10_錯誤處理與狀態規範.md` 第 3 節)。

Access token **不做撤銷**:JWT 的驗證是離線的,要即時撤銷就得每次請求查一次資料庫,等於放棄 JWT 的唯一好處。Web 的撤銷透過 refresh token(1 小時內最終失效),App 因 token 效期 180 天,撤銷手段只有刪除帳號後其他服務查不到資料——這是刻意接受的限制,見 `05_spec_帳號設定.md` 第 2.1 節。

## 3. API 介面

| Method | Path | 說明 |
|---|---|---|
| POST | `/auth/register` | 註冊帳號 |
| POST | `/auth/login` | 登入,依 `platform` 參數簽發對應 token |
| POST | `/auth/oauth/login` | 第三方登入(Google/Apple),驗證 provider id_token 後依 `platform` 參數簽發對應 token,見 2.7 節 |
| POST | `/auth/token/refresh` | Web 專用:用 refresh token 換發新的 access token(rotation) |
| POST | `/auth/token/extend` | App 專用:token 核發滿 7 天時展延效期,見 2.3.2 節;未滿 7 天回 `204` |
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

`AUTH_005` 的回應 body 於 `error` 之外另帶 `retry_after_seconds`(整數秒),供前端顯示倒數;鎖定中的帳號無論密碼是否正確都回本碼。忘記密碼端點超過 2.4 節限流時回全域 `RATE_001`。

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
- [ ] 不存在的 email 連續登入失敗 5 次,回應與存在帳號完全相同(同樣是 AUTH_005),無法藉此列舉帳號
- [ ] 鎖定期間即使輸入正確密碼仍回 AUTH_005,且回應帶 retry_after_seconds
- [ ] `A@X.com` 與 `a@x.com` 視為同一帳號:前者註冊後,後者登入成功;重複註冊回 AUTH_004 而非 500
- [ ] 密碼含非 ASCII 字元或超過 72 bytes 時回 AUTH_006
- [ ] 已撤銷的 refresh token 再次用於換發時,該使用者所有 refresh token 一併被撤銷(重放偵測)
- [ ] 同一 refresh token 併發換發兩次,只有一次成功,另一次回 AUTH_010
- [ ] 登出對不存在/已撤銷的 refresh token 一律回 204(冪等)
- [ ] App token 核發未滿 7 天時 `POST /auth/token/extend` 回 204;滿 7 天回傳新 token 且 `iat` 已更新
- [ ] 第三方登入 id_token 的 `email_verified` 不為真時,即使 email 與既有帳號相符也不綁定,回 AUTH_011
- [ ] 密碼重設 token 使用一次後即失效(第二次使用回 AUTH_007)
- [ ] 重設密碼成功後,該帳號原有的 refresh token 全部失效
- [ ] 忘記密碼端點同一 email 一小時內超過 5 次回 RATE_001
- [ ] 寄信失敗時對外仍回傳與成功相同的訊息
