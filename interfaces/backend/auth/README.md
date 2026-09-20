# Auth 服務

涵蓋 F0.1(登入註冊與密碼重設)與 F0.4(帳號設定)。擁有 `users`、`refresh_tokens`、
`oauth_identities`、`password_reset_tokens` 四張表(見
`rule_doc/功能需求/13_ADR_微服務與三節點部署.md` 第 1 節)。

本服務是系統中**唯一簽發 access token** 的地方;其餘六個服務拿同一把共用密鑰只做驗證。

對外契約在 `interfaces/backend/auth/__init__.py`,`tests/test_contract.py` 驗證實作不走樣。

## 規格審查結論

開發前對 `02_spec_登入註冊與密碼重設.md`、`05_spec_帳號設定.md` 做過一輪對抗式審查,
結論為 🔴(有阻斷問題)。以下是已確認並回寫進規格書的修改:

| # | 問題 | 處置 |
|---|------|------|
| 1 | `oauth_identities` 未指派給任何服務,但第三方登入非 Auth 不可實作 | 歸 Auth 擁有,補進 ADR 第 1 節與本服務契約 |
| 2 | 密碼重設 token(30 分鐘、一次性)沒有儲存位置 | 新增 `password_reset_tokens` 表(01 規格第 2.9 節)。不放 Redis:Redis 不持久化,重啟會讓已寄出的連結全部失效 |
| 3 | 登入失敗鎖定計數沒有儲存位置 | `users` 新增 `failed_login_attempts`、`locked_until`。不放 Redis:重啟清空鎖定等於一個可被主動觸發的暴力破解旁路 |
| 4 | 第三方登入自動綁定未檢查 `email_verified` → 帳號接管 | 02 規格第 2.7 節明訂未驗證一律回 `AUTH_011` |
| 5 | 刪除帳號的跨服務串聯沒有端點、沒有失敗補償 | Device 補 `DELETE /internal/users/{user_id}/devices`;Auth 依序呼叫 Device → Album,全部成功才刪 `users`,任一失敗回 `SRV_002`,兩端點都要求冪等(05 規格第 2.2 節) |
| 6 | 「任一已登入 API 夾帶新 token」與「其餘服務只驗證不簽發」矛盾 | 改為 Auth 專責的 `POST /auth/token/extend`(02 規格第 2.3.2 節) |
| 7 | 鎖定只對存在的帳號生效 → 帳號列舉器,與反列舉設計互斥 | 計數鍵改為送入的 email 字串,不存在的帳號以 Redis `login:fail:{email}` 承接,回應完全相同(02 規格第 2.3 節) |

### 開發中才發現的第 8 個阻斷問題(TDD 過程補記)

| # | 問題 | 處置 |
|---|------|------|
| 8 | 「改密碼保留當前 session」實作不出來,而且實作出來會自相矛盾 | 見下方兩段 |

寫 e2e 時才浮出來的兩件事:

**(a) 後端無從得知哪一個是「當前 session」。** access token 的 claim 只有
`sub`/`iat`/`exp`/`platform`(§2.8),沒有任何東西指得出 `refresh_tokens` 的哪一列。
處置:`PATCH /auth/password` 的 request body 新增選填的 `current_refresh_token`,
由 Web 用戶端帶上自己手上的那一個(它本來就要帶去 `/auth/logout`)。App 沒有
refresh token,省略即可。**`02_spec` §2.8 的 claim 集合不必改。**

**(b) 撤銷之後,無辜的用戶端看起來跟竊賊一模一樣。** 改密碼撤銷了另一個分頁的
token;那個分頁下次自動換發時送上來的是一個「已撤銷的 token」——正好命中 §2.3.1
的重放偵測,於是連我們刻意保留的當前 session 也被一起撤銷,`05_spec` §2.1 的
「不強制登出當前 session」形同虛設。處置:`refresh_tokens` 新增 `revoked_reason`
(`rotated` / `logged_out` / `superseded`),**重放偵測只對 `rotated` 生效**。
登出與改密碼造成的撤銷是我們主動做的,那個用戶端根本不知情,不該被當成竊取者。

另有 11 項🟡(JWT claim 格式、登出 request body、refresh token 重放偵測與併發、
註冊唯一性競態、email 正規化、密碼 72 **bytes** 上限、`retry_after_seconds`、
忘記密碼限流與寄信失敗處理、改密碼撤銷其他 session)同樣已寫進規格書,
逐條對應見兩份 spec 的第 6 節驗收標準。

**已知且刻意接受的限制**:App 的 access token 效期 180 天且不做撤銷,因此改密碼與
刪除帳號都無法立即使既有 App token 失效(02 規格第 2.8 節、05 規格第 2.1 節)。

## 領域地圖

第一層按業務領域切,第二層才是技術分層。

| 領域 | 一句話職責 | 擁有的表 | 對外 use case |
|---|---|---|---|
| `accounts` | 帳號身分與憑證:誰是這個人、他的密碼算不算數 | `users`、`oauth_identities`、`password_reset_tokens` | Register、Login、RequestPasswordReset、ResetPassword、ChangePassword、DeleteAccount |
| `sessions` | 已驗明身分之後,發什麼 token、發多久、怎麼收回 | `refresh_tokens` | IssueTokens、RefreshTokens、ExtendAppToken、Logout |

拆成兩個而不是一個,是因為**變動理由不同**:`accounts` 的規則隨安全政策變動
(密碼強度、鎖定次數、第三方綁定條件),`sessions` 的規則隨用戶端需求變動
(平台效期差異、rotation、滑動展延,02 規格第 2.6 節整張表都是 sessions 的事)。
`users.failed_login_attempts` 雖然是登入才用得到,但它屬於「這組憑證算不算數」的判斷,
因此歸 `accounts`。

跨領域只有一個方向:`accounts` 的登入/改密碼/重設密碼需要簽發或撤銷 session,
因此 `accounts/application/ports.py` 定義自己語言的 port `SessionService`
(`issue(user_id, platform)`、`revoke_all(user_id, except_=None)`),
由 `accounts/infrastructure/sessions_adapter.py` 接到 `sessions/api.py`。
`sessions` 完全不知道 `accounts` 存在。

外部依賴一律是 port,正式實作在 infrastructure:

| port | 用途 | 正式實作 |
|---|---|---|
| `PasswordHasher` | bcrypt 雜湊與驗證 | `bcrypt` |
| `SecretGenerator` | 重設 token / refresh token 的密碼學亂數 | `secrets.token_urlsafe` |
| `EmailSender` | 寄出重設連結;失敗只記 log(02 規格第 2.4 節) | 依部署環境 |
| `LoginAttemptTracker` | 不存在帳號的失敗計數(Redis,fail-open) | Redis |
| `AccountPurger` × 2 | Device / Album 的內部端點 | httpx + `X-Internal-Api-Key` |
| `AccessTokenSigner` | JWT 簽發(只有本服務有) | PyJWT |
| `Clock` / `IdGenerator` | 時間與 UUIDv7 由外部注入,domain 不自己取 | `app/core/system.py` |

## 本輪範圍

F0.1 的 email/密碼流程 + F0.4 全部。**第三方登入(02 規格第 2.7 節)留待第二輪**——
端到端驗證需要 Google/Apple 的 client ID,先把核心跑起來。契約中的 `OAuthIdentity`
與 `OAuthIdentityRepository` 先定義好,刪除帳號的串聯清除已涵蓋該表。

## 測試清單

由內而外推進,每一項對應規格的一條驗收標準。

### accounts / domain — 業務規則在這裡窮盡
- [x] Email 正規化:大小寫與頭尾空白一律轉為小寫並去空白(§2.1)
- [x] Email 格式不符、或超過 254 字元 → `InvalidEmail`(VAL_001)
- [x] 密碼少於 8 碼 → `WeakPassword`(AUTH_006)
- [x] 密碼超過 72 bytes → `WeakPassword`(§2.1,bcrypt 上限以位元組計)
- [x] 密碼含非可列印 ASCII 字元 → `WeakPassword`
- [x] 密碼缺英文字母或缺數字 → `WeakPassword`
- [x] 帳密驗證成功 → 失敗計數歸零
- [x] 帳密驗證失敗第 1~4 次 → `InvalidCredentials`(AUTH_003),計數遞增、未鎖定
- [x] 第 5 次失敗 → `locked_until = now + 15 分`(§2.3)
- [x] 鎖定期間即使密碼正確 → `AccountLocked`(AUTH_005),且不重置計數
- [x] `AccountLocked` 帶 `retry_after_seconds`(§5)
- [x] 鎖定期滿後的第一次嘗試 → 計數先歸零再重新計算
- [x] `password_hash` 為 None 的帳號永遠無法以密碼登入(§2.7)
- [x] 已設過密碼的帳號改密碼需附目前密碼,錯誤 → `InvalidCurrentPassword`(AUTH_008)(05 §2.1)
- [x] `password_hash` 為 None 的帳號設定密碼免附目前密碼(05 §2.1)
- [x] 重設 token 已過期或已使用 → `InvalidResetToken`(AUTH_007)

### accounts / application — 只驗流程編排
- [x] Register:email 重複(repository 拋衝突)→ AUTH_004,且未 commit
- [x] Register:成功時 commit 一次,寫入的是雜湊、明碼不出現在任何寫入參數
- [x] Register:`A@X.com` 與既有 `a@x.com` 視為同一帳號 → AUTH_004(§2.1)
- [x] Login:帳號不存在 → AUTH_003,且以 email 為鍵累計 `LoginAttemptTracker`
- [x] Login:不存在的 email 連續 5 次 → AUTH_005,回應與存在帳號完全相同(§2.3,審查 #7)
- [x] Login:`LoginAttemptTracker` 失效時 fail-open,不鎖定也不讓請求失敗
- [x] Login:成功 → 呼叫 `SessionService.issue(user_id, platform)`,commit 一次
- [x] Login:密碼錯誤仍要 commit(失敗計數必須寫入)
- [x] RequestPasswordReset:email 不存在 → 回成功、不寄信、不建立 token(§2.4)
- [x] RequestPasswordReset:email 存在 → 建立 token(存雜湊)、寄出的連結帶明碼
- [x] RequestPasswordReset:寄信失敗 → 仍回成功(§2.4)
- [x] RequestPasswordReset:同一 email 一小時內第 6 次 → RATE_001(§2.4)
- [x] ResetPassword:成功 → 更新雜湊、`mark_used`、撤銷該使用者全部 refresh token、commit
- [x] ResetPassword:`mark_used` 回 False(重複點擊/併發)→ AUTH_007,密碼不變
- [x] ResetPassword:新密碼不符規則 → AUTH_006,且 token 未被消耗
- [x] ChangePassword:成功 → 撤銷其他 refresh token、以 `exclude_id` 保留當前(05 §2.1)
- [x] DeleteAccount:密碼確認錯 → AUTH_009,且未呼叫任何內部端點
- [x] DeleteAccount:`password_hash` 為 None 時以 email 文字確認,不符 → VAL_001(05 §2.2)
- [x] DeleteAccount:Device 端點失敗 → SRV_002,`users` 未刪除,Album 端點未被呼叫
- [x] DeleteAccount:Album 端點失敗 → SRV_002,`users` 未刪除
- [x] DeleteAccount:全成功 → 依序 Device → Album,最後刪除 `users`,commit 一次

### sessions / domain
- [x] Web 簽發:access `exp = iat + 1h`、refresh `exp = iat + 30d`(§2.6)
- [x] App 簽發:access `exp = iat + 180d`,且不產生 refresh token(§2.3.2)
- [x] claim 集合為 `sub` / `iat` / `exp` / `platform`(§2.8)
- [x] 已撤銷或已過期的 refresh token 不可用
- [x] App token `iat` 未滿 7 天 → 不需展延;滿 7 天 → 需展延(§2.3.2)

### sessions / application
- [x] IssueTokens(web):回傳明碼 refresh token,資料庫只存雜湊
- [x] IssueTokens(app):不寫入 `refresh_tokens`
- [x] RefreshTokens:token 不存在或已過期 → AUTH_010
- [x] RefreshTokens:token 已撤銷 → 撤銷該使用者全部未撤銷 token,再回 AUTH_010(§2.3.1 重放偵測)
- [x] RefreshTokens:`revoke` 回 False(併發輸家)→ 視為重放,AUTH_010
- [x] RefreshTokens:成功 → 舊的標記撤銷、新的寫入、commit 一次
- [x] ExtendAppToken:未滿 7 天 → 回 None(由 router 轉 204)
- [x] ExtendAppToken:滿 7 天 → 新 token 的 `iat` 為當下、`exp` 為 +180 天
- [x] ExtendAppToken:`platform` 為 web 的 token → AUTH_001(展延是 App 專用)
- [x] Logout:未知或已撤銷的 token → 不拋例外(§2.5 冪等)

### contract — fake 與 SQLAlchemy 跑同一份

每一項都以 `params=["fake", "sqlalchemy"]` 跑兩次。fake 那一半已綠;
SQLAlchemy 那一半需要 `AUTH_TEST_DATABASE_URL`,未設定時跳過(見下方「尚待處理」)。
- [x] `UserRepository`:查無回 None、commit 後可取回、未 commit 回滾、email 重複 create 拋衝突、失敗計數的寫入與歸零生效
- [x] `RefreshTokenRepository`:`revoke` 第一次 True、第二次 False;`revoke_all_by_user` 回傳筆數且不動已撤銷者;`exclude_id` 確實被保留
- [x] `PasswordResetTokenRepository`:`mark_used` 第一次 True、第二次 False

### infrastructure — 真實 PostgreSQL,不用 SQLite 代替

**已寫好但尚未執行**:需要 `AUTH_TEST_DATABASE_URL` 指向一個可建表的資料庫。
用 SQLite 跑這幾項會綠,但綠得毫無意義——它對 CHECK、CASCADE、timestamptz、
條件 UPDATE 的語意都與 PostgreSQL 不同。
- [ ] `CHECK email = lower(email)`:直接寫入大寫 email 會失敗(證明正規化非做不可)
- [ ] email 唯一約束違反被轉成領域的衝突例外,IntegrityError 不外漏
- [ ] `locked_until` 存取後時區完整還原(timestamptz)
- [ ] 刪除 `users` 後三張子表由 `ON DELETE CASCADE` 一併消失
- [ ] `revoke` 的條件更新在併發下只有一個回 True
- [ ] migration `0002` upgrade / downgrade 可往返

### presentation — 只測 HTTP 契約
- [x] `POST /auth/register` email 格式錯 → 400 + `VAL_001`
- [x] `POST /auth/register` 弱密碼 → 400 + `AUTH_006`;email 重複 → 409 + `AUTH_004`
- [x] `POST /auth/login` 帳密錯 → 401 + `AUTH_003`
- [x] `POST /auth/login` 鎖定 → 423 + `AUTH_005` + `retry_after_seconds`
- [x] `POST /auth/login` `platform=web` 回 access+refresh、`platform=app` 只回 access
- [x] `POST /auth/login` `platform` 非 app/web → 400 + `VAL_001`
- [x] `POST /auth/token/refresh` 無效 → 401 + `AUTH_010`
- [x] `POST /auth/token/extend` 未滿 7 天 → 204
- [x] `POST /auth/logout` 未知 token → 204
- [x] `POST /auth/password/forgot` 不存在的 email → 200,訊息與存在時完全相同
- [x] `POST /auth/password/reset` 過期 token → 410 + `AUTH_007`
- [x] `PATCH /auth/password` 未帶 token → 401 + `AUTH_001`;目前密碼錯 → 401 + `AUTH_008`
- [x] `DELETE /auth/account` 密碼錯 → 401 + `AUTH_009`;內部端點失敗 → 503 + `SRV_002`
- [x] 所有端點的回應都不含 `password_hash`

### e2e
- [x] 註冊 → web 登入 → 改密碼 → 其他 refresh token 失效、當前仍可用 → 新密碼可登入
- [x] 忘記密碼 → 以信中 token 重設 → 舊密碼登入失敗、新密碼成功、原 refresh token 全失效

## 尚待處理

| 項目 | 說明 |
|---|---|
| `db/` 的 `revoked_reason` 欄位 | 上面問題 8(b) 新增的欄位,本服務的 ORM 已有,但 `db/models.py` 與一支新的 migration(`0003`)還沒加——`db/` 不在這個 worktree 裡。另需把 `01_資料模型與儲存規格.md` 第 2.5 節補上該欄位 |
| `rule_doc` 同步 | 問題 8 的兩個處置要寫回 `05_spec` 第 2.1、3 節(request body 的 `current_refresh_token`)與 `02_spec` 第 2.3.1 節(重放偵測的適用範圍)。Phase 0 的規格修改留在 main 的工作區,尚未提交 |
| 6 項 infrastructure 測試 | 已寫好,需要 `AUTH_TEST_DATABASE_URL`。本機 PostgreSQL 有跑,但 `pet_camera_migrate` 的密碼與 `db/.env.example` 的預設值不同,沒有憑證 |
| 第三方登入(F0.1 §2.7) | 第二輪。契約中的 `OAuthIdentity` / `OAuthIdentityRepository` 已定義,刪除帳號的串聯清除已涵蓋該表 |
| `EmailSender` 的正式實作 | 目前掛的是 `LoggingEmailSender`(**正式環境不可用**:重設連結等同一次性登入憑證,寫進 log 就是散佈它)。`SmtpEmailSender` 已備好,待部署環境提供 SMTP 設定 |

## 覆蓋率

`domain` 與 `application` 兩層 **100%**,唯一沒被覆蓋的是
`accounts/domain/entities.py` 的 `_retry_after_seconds` 在 `locked_until is None`
時的防禦性 `return 0`——該方法只在鎖定成立時才會被呼叫,這一行走不到。

`infrastructure` 約 50%,缺的正是上面那 6 項需要真實資料庫的測試;
整體 86%。

## 開發指令

```bash
uv sync
uv run pytest -q
uv run pytest --cov=app --cov-report=term-missing
uv run python tools/check_layers.py --root .

# 連同需要真實 PostgreSQL 的那一半(會建表與刪表,不要指到有資料的庫)
AUTH_TEST_DATABASE_URL=postgresql+asyncpg://user:pw@localhost/pet_camera_test \
    uv run pytest
uv run ruff check . && uv run mypy app
```
