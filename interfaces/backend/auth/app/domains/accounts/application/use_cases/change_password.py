"""修改密碼 / 設定密碼(05_spec_帳號設定.md 第 2.1 節)。

「要不要附目前密碼」是實體的規則(有沒有 password_hash),不是這裡的 if/else;
這裡只負責載入、呼叫、保存,以及事後撤銷其他 session。
"""

from app.domains.accounts.application.dtos import ChangePasswordCommand
from app.domains.accounts.application.ports import AccountsUnitOfWork, SessionService
from app.domains.accounts.domain.exceptions import AccountNotFound
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import RawPassword
from app.shared_kernel.ports import Clock


class ChangePassword:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        *,
        hasher: PasswordHasher,
        clock: Clock,
        sessions: SessionService,
    ) -> None:
        self.uow = uow
        self.hasher = hasher
        self.clock = clock
        self.sessions = sessions

    async def execute(self, command: ChangePasswordCommand) -> None:
        new_password = RawPassword.parse(command.new_password)
        # 目前密碼只是用來比對,不套用強度規則——舊密碼合不合規不是現在的問題
        current = (
            RawPassword(command.current_password)
            if command.current_password is not None
            else None
        )

        async with self.uow:
            user = await self.uow.users.get(command.user_id)
            if user is None:
                raise AccountNotFound()

            user.change_password(
                current=current,
                new=new_password,
                hasher=self.hasher,
                now=self.clock.now(),
            )
            await self.uow.users.save(user)
            await self.uow.commit()

        # 撤銷其他 session,保留當前這一個(05_spec 第 2.1 節)
        await self.sessions.revoke_all(
            command.user_id, except_refresh_token=command.current_refresh_token
        )
