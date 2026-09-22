"""Auth 服務——涵蓋 F0.1(登入註冊密碼重設)+ F0.4(帳號設定)。

擁有 users、refresh_tokens、oauth_identities、password_reset_tokens 四張表。
F0.4 併入本服務而非獨立成一個服務,理由見
rule_doc/功能需求/13_ADR_微服務與三節點部署.md 第 1 節。

本服務是系統中唯一**簽發** access token 的地方;其餘六個服務只用共用密鑰驗證
(claim 格式見 02_spec_登入註冊與密碼重設.md 第 2.8 節)。

本檔是**對外契約**;實作在 app/domains/ 底下,tests/test_contract.py 驗證兩者不會走樣。

規格審查後對原始介面與規格的修改(見 README 的「規格審查結論」):
- 新增 OAuthIdentity / OAuthIdentityRepository:原契約只列 users、refresh_tokens,
  但 02_spec 第 2.7 節的第三方登入非本服務不可實作(ADR 第 1 節已補上擁有權)。
- 新增 PasswordResetToken / PasswordResetTokenRepository:原本重設 token 沒有任何
  儲存位置(02_spec 第 2.4 節),共用 Redis 的用途又已明定固定三項。
- User 新增 failed_login_attempts / locked_until:原本登入失敗鎖定的計數同樣無處可存。
- RefreshTokenRepository.revoke 改為回傳 bool:rotation 併發時要靠「這次是否真的由我
  撤銷」判定勝負,否則一個 refresh token 可能換出兩組有效 token(02_spec 第 2.3.1 節)。
- 新增 revoke_all_by_user:重放偵測、修改密碼、重設密碼三處都要連帶撤銷其他 session。
- create 的 password_hash 改為可選:純第三方登入建立的帳號為 null(02_spec 第 2.7 節)。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel

# 02_spec 第 2.1 節:bcrypt 的雜湊輸入上限是 72 bytes,密碼限定可列印 ASCII,
# 因此字元數等於位元組數。
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72
EMAIL_MAX_LENGTH = 254

# 02_spec 第 2.3 節
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

# 02_spec 第 2.3.1、2.3.2、2.4 節
WEB_ACCESS_TOKEN_HOURS = 1
WEB_REFRESH_TOKEN_DAYS = 30
APP_ACCESS_TOKEN_DAYS = 180
APP_TOKEN_EXTEND_AFTER_DAYS = 7
PASSWORD_RESET_TTL_MINUTES = 30


class Platform(str, Enum):
    APP = "app"
    WEB = "web"


class OAuthProvider(str, Enum):
    GOOGLE = "google"
    APPLE = "apple"


class User(BaseModel):
    id: UUID
    email: str  # 一律小寫儲存(01_資料模型 第 2.1 節的 CHECK 約束)
    # 僅透過第三方登入建立、尚未設定過密碼的帳號為 None(02_spec 第 2.7 節)
    password_hash: Optional[str] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    created_at: datetime


class RefreshToken(BaseModel):
    """僅 Web 平台使用(見 02_spec_登入註冊與密碼重設.md 第 2.3.1 節)。"""

    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime


class OAuthIdentity(BaseModel):
    """第三方登入的身分綁定(02_spec 第 2.7 節)。

    與 Album 服務的 GoogleDriveCredential 不是同一件事:那是「把相簿匯出到使用者的
    Google Drive」的 drive.file 授權,這是「用 Google/Apple 帳號登入本系統」。
    """

    id: UUID
    user_id: UUID
    provider: OAuthProvider
    provider_user_id: str
    # Apple 僅在首次授權回傳 email,之後的登入可能沒有(01_資料模型 第 2.7 節)
    email: Optional[str] = None
    created_at: datetime


class PasswordResetToken(BaseModel):
    """忘記密碼的一次性重設 token(02_spec 第 2.4 節)。只存雜湊值,不存明碼。"""

    id: UUID
    user_id: UUID
    token_hash: str
    expires_at: datetime
    used_at: Optional[datetime] = None
    created_at: datetime


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> Optional[User]: ...

    async def get_by_email(self, email: str) -> Optional[User]:
        """email 需由呼叫端先正規化為小寫(02_spec 第 2.1 節)。"""
        ...

    async def create(self, email: str, password_hash: Optional[str]) -> User:
        """password_hash 為 None 代表純第三方登入建立的帳號。

        email 重複時拋出衝突例外,由呼叫端轉為 AUTH_004——不以「先查再寫」判斷,
        否則兩個同時的註冊請求會雙雙通過檢查(02_spec 第 2.2 節)。
        """
        ...

    async def update_password_hash(self, user_id: UUID, password_hash: str) -> None: ...

    async def record_login_failure(
        self, user_id: UUID, *, attempts: int, locked_until: Optional[datetime]
    ) -> None:
        """寫入新的失敗次數與鎖定到期時間;該不該鎖、鎖多久由 domain 決定。"""
        ...

    async def clear_login_failures(self, user_id: UUID) -> None:
        """登入成功、或鎖定期滿後的第一次嘗試,計數歸零。"""
        ...

    async def delete(self, user_id: UUID) -> None:
        """僅刪除 users 這筆紀錄;本服務自己的三張子表由外鍵 ON DELETE CASCADE 帶走。

        呼叫前 service 層需已完成資料模型文件第 6 節的跨服務清除
        (Device 與 Album 的內部端點,見 05_spec_帳號設定.md 第 2.2 節),
        任一步驟失敗就不應該走到這裡。
        """
        ...


class RefreshTokenRepository(Protocol):
    async def get_by_token_hash(self, token_hash: str) -> Optional[RefreshToken]: ...

    async def create(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> RefreshToken: ...

    async def revoke(self, refresh_token_id: UUID, *, revoked_at: datetime) -> bool:
        """登出,或 rotation 換發新 token 時,將舊紀錄標記撤銷。

        回傳「本次呼叫是否真的完成撤銷」:已經是撤銷狀態時回 False。rotation 的併發
        勝負就靠這個回傳值判定,False 者視為重放(02_spec 第 2.3.1 節)。
        """
        ...

    async def revoke_all_by_user(
        self, user_id: UUID, *, revoked_at: datetime, exclude_id: Optional[UUID] = None
    ) -> int:
        """撤銷該使用者所有未撤銷的 token,回傳撤銷筆數。

        三處會用到:偵測到 refresh token 重放、修改密碼(保留當前 session,以
        exclude_id 指定)、重設密碼(不保留)。
        """
        ...

    async def delete_all_by_user(self, user_id: UUID) -> None:
        """刪除帳號時串聯清除。"""
        ...


class OAuthIdentityRepository(Protocol):
    async def get_by_provider_user_id(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> Optional[OAuthIdentity]: ...

    async def create(
        self,
        user_id: UUID,
        *,
        provider: OAuthProvider,
        provider_user_id: str,
        email: Optional[str],
    ) -> OAuthIdentity:
        """同一 provider 帳號重複綁定、或同一使用者在同一 provider 綁第二個帳號時,
        拋出衝突例外(01_資料模型 第 2.7 節的兩個唯一索引)。"""
        ...

    async def delete_all_by_user(self, user_id: UUID) -> None:
        """刪除帳號時串聯清除。"""
        ...


class PasswordResetTokenRepository(Protocol):
    async def get_by_token_hash(self, token_hash: str) -> Optional[PasswordResetToken]: ...

    async def create(
        self, user_id: UUID, token_hash: str, expires_at: datetime
    ) -> PasswordResetToken: ...

    async def mark_used(self, reset_token_id: UUID, *, used_at: datetime) -> bool:
        """標記為已使用,回傳「本次呼叫是否真的完成標記」。

        同一個連結被點兩次時,只有一次能回 True;False 者一律回 AUTH_007。
        """
        ...

    async def delete_all_by_user(self, user_id: UUID) -> None:
        """刪除帳號時串聯清除。"""
        ...
