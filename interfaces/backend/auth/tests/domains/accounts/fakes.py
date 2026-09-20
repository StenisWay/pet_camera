"""測試替身:有真實行為的 fake,不是 mock。

每個 fake 都明確繼承正式介面,和 infrastructure 的實作是「同一份合約的兩個實作」,
由 tests/domains/accounts/contracts/ 的合約測試保證兩者行為一致。
"""

import copy
import uuid
from datetime import datetime
from typing import Self

from app.domains.accounts.application.ports import (
    AccountPurger,
    AccountsUnitOfWork,
    EmailSender,
    IssuedSession,
    LoginAttemptTracker,
    PasswordResetThrottle,
    SessionService,
)
from app.domains.accounts.domain.entities import PasswordResetToken, User
from app.domains.accounts.domain.exceptions import EmailAlreadyRegistered
from app.domains.accounts.domain.repositories import (
    PasswordResetTokenRepository,
    UserRepository,
)
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.errors import RateLimited
from app.shared_kernel.platform import Platform
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory


class _Store:
    """兩個 repository 共用的「資料庫」:committed 是已提交,pending 是本次交易。"""

    def __init__(self) -> None:
        self.users: dict[uuid.UUID, User] = {}
        self.reset_tokens: dict[uuid.UUID, PasswordResetToken] = {}


class FakeUserRepository(UserRepository):
    def __init__(self, committed: dict[uuid.UUID, User]) -> None:
        self._committed = committed
        self.pending: dict[uuid.UUID, User] = {}
        self.deleted: set[uuid.UUID] = set()

    def _visible(self) -> dict[uuid.UUID, User]:
        merged = {**self._committed, **self.pending}
        return {k: v for k, v in merged.items() if k not in self.deleted}

    async def get(self, user_id: uuid.UUID) -> User | None:
        # 回傳複本:模擬「從資料庫載入」,忘了 save 的修改不會被保存
        return copy.deepcopy(self._visible().get(user_id))

    async def get_by_email(self, email: Email) -> User | None:
        for user in self._visible().values():
            if user.email == email:
                return copy.deepcopy(user)
        return None

    async def add(self, user: User) -> None:
        if await self.get_by_email(user.email) is not None:
            raise EmailAlreadyRegistered()
        self.pending[user.id] = copy.deepcopy(user)

    async def save(self, user: User) -> None:
        self.pending[user.id] = copy.deepcopy(user)

    async def delete(self, user_id: uuid.UUID) -> None:
        self.deleted.add(user_id)


class FakePasswordResetTokenRepository(PasswordResetTokenRepository):
    def __init__(self, committed: dict[uuid.UUID, PasswordResetToken]) -> None:
        self._committed = committed
        self.pending: dict[uuid.UUID, PasswordResetToken] = {}

    def _visible(self) -> dict[uuid.UUID, PasswordResetToken]:
        return {**self._committed, **self.pending}

    async def get_by_fingerprint(self, fingerprint: str) -> PasswordResetToken | None:
        for token in self._visible().values():
            if token.token_hash == fingerprint:
                return copy.deepcopy(token)
        return None

    async def add(self, token: PasswordResetToken) -> None:
        self.pending[token.id] = copy.deepcopy(token)

    async def mark_used(self, token_id: uuid.UUID, *, used_at: datetime) -> bool:
        # 條件更新:只有「目前還沒被用過」才算這次標記成功
        token = self._visible().get(token_id)
        if token is None or token.used_at is not None:
            return False
        updated = copy.deepcopy(token)
        updated.used_at = used_at
        self.pending[token_id] = updated
        return True


class FakeAccountsUnitOfWork(AccountsUnitOfWork):
    # 收窄成具體型別,測試才能斷言 pending/commits 這些 fake 專屬的觀察點
    users: FakeUserRepository
    reset_tokens: FakePasswordResetTokenRepository

    def __init__(self) -> None:
        self._store = _Store()
        self.commits = 0
        self.users = FakeUserRepository(self._store.users)
        self.reset_tokens = FakePasswordResetTokenRepository(self._store.reset_tokens)

    async def __aenter__(self) -> Self:
        self.users = FakeUserRepository(self._store.users)
        self.reset_tokens = FakePasswordResetTokenRepository(self._store.reset_tokens)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        # 未 commit 的 pending 直接丟棄 = 回滾
        self.users.pending.clear()
        self.reset_tokens.pending.clear()

    async def commit(self) -> None:
        self.commits += 1
        self._store.users.update(self.users.pending)
        for user_id in self.users.deleted:
            self._store.users.pop(user_id, None)
        self._store.reset_tokens.update(self.reset_tokens.pending)
        self.users.pending.clear()
        self.reset_tokens.pending.clear()


class FakePasswordHasher(PasswordHasher):
    """可逆但不透明:形狀與 bcrypt 一樣是一個字串,內容不是明碼。"""

    def hash(self, raw: RawPassword) -> str:
        return "hashed:" + raw.value

    def verify(self, raw: RawPassword, password_hash: str) -> bool:
        return password_hash == "hashed:" + raw.value


class FixedClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance_to(self, now: datetime) -> None:
        self._now = now


class SequentialIdGenerator(IdGenerator):
    """確定性 ID:測試斷言得出來,也看得出誰先被建立。"""

    def __init__(self) -> None:
        self._counter = 0

    def new_id(self) -> uuid.UUID:
        self._counter += 1
        return uuid.UUID(int=self._counter)


class FakeTokenFactory(OpaqueTokenFactory):
    def __init__(self) -> None:
        self._counter = 0
        self.generated: list[str] = []

    def generate(self) -> str:
        self._counter += 1
        secret = f"secret-{self._counter}"
        self.generated.append(secret)
        return secret

    def fingerprint(self, secret: str) -> str:
        return "fp:" + secret


class FakeSessionService(SessionService):
    def __init__(self) -> None:
        self.issued: list[tuple[uuid.UUID, Platform]] = []
        self.revoked: list[tuple[uuid.UUID, uuid.UUID | None]] = []

    async def issue(self, user_id: uuid.UUID, platform: Platform) -> IssuedSession:
        self.issued.append((user_id, platform))
        return IssuedSession(
            access_token=f"access-for-{user_id}",
            refresh_token=f"refresh-for-{user_id}" if platform.uses_refresh_token else None,
        )

    async def revoke_all(
        self, user_id: uuid.UUID, *, except_token_id: uuid.UUID | None = None
    ) -> None:
        self.revoked.append((user_id, except_token_id))


class FakeLoginAttemptTracker(LoginAttemptTracker):
    def __init__(self, *, unavailable: bool = False) -> None:
        self.failures: dict[str, int] = {}
        self.locked: dict[str, int] = {}
        self.unavailable = unavailable

    async def remaining_lockout_seconds(self, email: str) -> int:
        if self.unavailable:
            return 0  # fail-open
        return self.locked.get(email, 0)

    async def register_failure(
        self, email: str, *, max_attempts: int, lockout_seconds: int
    ) -> int:
        if self.unavailable:
            return 0  # fail-open
        self.failures[email] = self.failures.get(email, 0) + 1
        if self.failures[email] >= max_attempts:
            self.locked[email] = lockout_seconds
            return lockout_seconds
        return 0


class FakePasswordResetThrottle(PasswordResetThrottle):
    def __init__(self, *, allow: bool = True) -> None:
        self.allow = allow
        self.checked: list[tuple[str, ...]] = []

    async def check(self, *identities: str) -> None:
        self.checked.append(identities)
        if not self.allow:
            raise RateLimited()


class FakeEmailSender(EmailSender):
    def __init__(self, *, fails: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fails = fails

    async def send_password_reset(self, to: str, *, reset_url: str) -> None:
        if self.fails:
            raise RuntimeError("smtp unavailable")
        self.sent.append((to, reset_url))


class FakeAccountPurger(AccountPurger):
    def __init__(self, name: str, *, fails: bool = False) -> None:
        self.name = name
        self.fails = fails
        self.purged: list[uuid.UUID] = []

    async def purge(self, user_id: uuid.UUID) -> None:
        if self.fails:
            raise RuntimeError(f"{self.name} unavailable")
        self.purged.append(user_id)
