"""accounts 領域的實體。純 Python,不依賴框架,也不是 ORM model。

時間與 ID 一律由外部傳入(now、id),實體不自己呼叫 datetime.now() 或 uuid7()——
鎖定期滿、token 過期這類規則否則無法確定地測試。
"""

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NoReturn

from app.domains.accounts.domain.exceptions import (
    AccountLocked,
    InvalidCredentials,
    InvalidCurrentPassword,
    InvalidResetToken,
)
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import Email, RawPassword

# 02_spec 第 2.3 節:連續 5 次登入失敗鎖定 15 分鐘
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


@dataclass
class User:
    id: uuid.UUID
    email: Email
    # 僅透過第三方登入建立、尚未設定過密碼的帳號為 None(02_spec 第 2.7 節)
    password_hash: str | None
    failed_login_attempts: int
    locked_until: datetime | None
    created_at: datetime

    @classmethod
    def register(
        cls,
        *,
        id: uuid.UUID,
        email: Email,
        password: RawPassword,
        hasher: PasswordHasher,
        now: datetime,
    ) -> "User":
        return cls(
            id=id,
            email=email,
            password_hash=hasher.hash(password),
            failed_login_attempts=0,
            locked_until=None,
            created_at=now,
        )

    def has_password(self) -> bool:
        return self.password_hash is not None

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now

    def authenticate(
        self, password: RawPassword, *, hasher: PasswordHasher, now: datetime
    ) -> None:
        """驗證帳密並更新失敗計數。成功時無回傳,失敗時拋例外。

        鎖定期間一律 AccountLocked,即使密碼正確也不放行——否則暴力破解只要
        在鎖定視窗內猜中就等於繞過了鎖定(02_spec 第 2.3 節)。
        """
        if self.is_locked(now):
            raise AccountLocked(self._retry_after_seconds(now))

        # 鎖定期已過:計數重新開始,不是接著上次的 5 繼續加
        self._clear_lockout()

        if self.password_hash is None or not hasher.verify(password, self.password_hash):
            self._fail_attempt(now)

        self.failed_login_attempts = 0

    def change_password(
        self,
        *,
        current: RawPassword | None,
        new: RawPassword,
        hasher: PasswordHasher,
        now: datetime,
    ) -> None:
        """修改密碼(已設過)或設定密碼(尚未設過,05_spec 第 2.1 節)。

        這裡的失敗不計入登入鎖定:§2.3 的計數只算 /auth/login,使用者在設定頁
        打錯目前密碼不該把自己鎖在門外。
        """
        current_hash = self.password_hash
        if current_hash is not None:
            if current is None or not hasher.verify(current, current_hash):
                raise InvalidCurrentPassword()

        self.password_hash = hasher.hash(new)

    def reset_password(self, new: RawPassword, *, hasher: PasswordHasher) -> None:
        """忘記密碼流程設定新密碼(02_spec 第 2.4 節)。

        不需要目前密碼——使用者正是因為忘記才走這條路;憑據是信裡的一次性 token,
        由 use case 負責驗證。順便解除鎖定:能收到那封信就等於證明了信箱所有權,
        沒理由讓他繼續被鎖在門外。
        """
        self.password_hash = hasher.hash(new)
        self.failed_login_attempts = 0
        self.locked_until = None

    def _fail_attempt(self, now: datetime) -> NoReturn:
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
            self.locked_until = now + LOCKOUT_DURATION
            raise AccountLocked(self._retry_after_seconds(now))
        raise InvalidCredentials()

    def _clear_lockout(self) -> None:
        if self.locked_until is not None:
            self.locked_until = None
            self.failed_login_attempts = 0

    def _retry_after_seconds(self, now: datetime) -> int:
        if self.locked_until is None:
            return 0
        return max(0, math.ceil((self.locked_until - now).total_seconds()))


# 02_spec 第 2.4 節:重設 token 有效期 30 分鐘
RESET_TOKEN_TTL = timedelta(minutes=30)


@dataclass
class PasswordResetToken:
    """忘記密碼的一次性重設 token。

    只有雜湊值進得了這個實體——明碼只存在於寄出的連結裡,資料庫與程式內部
    都拿不到,所以 DB 外洩不等於可以重設任何人的密碼(02_spec 第 2.4 節)。
    """

    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    used_at: datetime | None
    created_at: datetime

    @classmethod
    def issue(
        cls, *, id: uuid.UUID, user_id: uuid.UUID, token_hash: str, now: datetime
    ) -> "PasswordResetToken":
        return cls(
            id=id,
            user_id=user_id,
            token_hash=token_hash,
            expires_at=now + RESET_TOKEN_TTL,
            used_at=None,
            created_at=now,
        )

    def ensure_usable(self, *, now: datetime) -> None:
        if self.used_at is not None or self.expires_at <= now:
            raise InvalidResetToken()
