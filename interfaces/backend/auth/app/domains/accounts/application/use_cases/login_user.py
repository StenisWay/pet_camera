"""帳密登入(02_spec 第 2.3 節)。

兩條路徑刻意在外部完全無法區分(規格審查 #7):

- 帳號存在:計數與鎖定狀態在 users 表(失敗計數必須 commit,否則永遠湊不滿 5 次)。
- 帳號不存在:沒有列可以寫,計數落在 LoginAttemptTracker。

若只對存在的帳號鎖定,「回 AUTH_005 還是 AUTH_003」本身就是一個帳號列舉器,
與 §2.4 刻意避免列舉的設計互相抵觸。
"""

from datetime import datetime
from typing import NoReturn

from app.domains.accounts.application.dtos import LoggedInUser, LoginCommand
from app.domains.accounts.application.ports import (
    AccountsUnitOfWork,
    LoginAttemptTracker,
    SessionService,
)
from app.domains.accounts.domain.entities import (
    LOCKOUT_DURATION,
    MAX_LOGIN_ATTEMPTS,
    User,
)
from app.domains.accounts.domain.exceptions import AccountLocked, InvalidCredentials
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import Email, RawPassword
from app.shared_kernel.ports import Clock

LOCKOUT_SECONDS = int(LOCKOUT_DURATION.total_seconds())


class LoginUser:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        *,
        hasher: PasswordHasher,
        clock: Clock,
        sessions: SessionService,
        attempts: LoginAttemptTracker,
    ) -> None:
        self.uow = uow
        self.hasher = hasher
        self.clock = clock
        self.sessions = sessions
        self.attempts = attempts

    async def execute(self, command: LoginCommand) -> LoggedInUser:
        # §2.1 的欄位規則涵蓋登入表單,不合規的輸入連查都不用查
        email = Email.parse(command.email)
        password = RawPassword.parse(command.password)
        now = self.clock.now()

        async with self.uow:
            user = await self.uow.users.get_by_email(email)
            if user is None:
                await self._fail_unknown_account(email)
            await self._authenticate(user, password, now=now)

        # 外部呼叫放在交易外:交易中不呼叫其他服務
        session = await self.sessions.issue(user.id, command.platform)
        return LoggedInUser(
            user_id=user.id,
            access_token=session.access_token,
            refresh_token=session.refresh_token,
        )

    async def _fail_unknown_account(self, email: Email) -> NoReturn:
        """不存在的帳號:回應必須與「帳號存在但密碼錯」完全一致。"""
        remaining = await self.attempts.remaining_lockout_seconds(email.value)
        if remaining > 0:
            raise AccountLocked(remaining)

        locked_for = await self.attempts.register_failure(
            email.value, max_attempts=MAX_LOGIN_ATTEMPTS, lockout_seconds=LOCKOUT_SECONDS
        )
        if locked_for > 0:
            raise AccountLocked(locked_for)
        raise InvalidCredentials()

    async def _authenticate(
        self, user: User, password: RawPassword, *, now: datetime
    ) -> None:
        try:
            user.authenticate(password, hasher=self.hasher, now=now)
        except (InvalidCredentials, AccountLocked):
            # 失敗計數是這次請求的產物,必須保存下來才算數
            await self.uow.users.save(user)
            await self.uow.commit()
            raise
        await self.uow.users.save(user)
        await self.uow.commit()
