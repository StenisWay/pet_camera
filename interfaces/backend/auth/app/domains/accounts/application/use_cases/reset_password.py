"""用信裡的一次性 token 設定新密碼(02_spec 第 2.4 節步驟 4、5)。

三件事的順序是刻意的:

1. **先驗密碼規則**,再碰 token。不合規就報銷連結,使用者只能回去重新申請,太粗暴。
2. **mark_used 的回傳值就是併發仲裁**。同一個連結被點兩次時,第二次影響 0 列,
   一律視為失效——不靠先讀後寫判斷,那有競態。
3. **撤銷所有 refresh token**。能重設密碼的人未必是原本持有 session 的人;
   帳號被盜的情境下,不撤銷等於改了密碼卻趕不走對方。
"""

from app.domains.accounts.application.dtos import ResetPasswordCommand
from app.domains.accounts.application.ports import AccountsUnitOfWork, SessionService
from app.domains.accounts.domain.exceptions import InvalidResetToken
from app.domains.accounts.domain.services import PasswordHasher
from app.domains.accounts.domain.value_objects import RawPassword
from app.shared_kernel.ports import Clock, OpaqueTokenFactory


class ResetPassword:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        *,
        hasher: PasswordHasher,
        clock: Clock,
        tokens: OpaqueTokenFactory,
        sessions: SessionService,
    ) -> None:
        self.uow = uow
        self.hasher = hasher
        self.clock = clock
        self.tokens = tokens
        self.sessions = sessions

    async def execute(self, command: ResetPasswordCommand) -> None:
        new_password = RawPassword.parse(command.new_password)
        now = self.clock.now()
        fingerprint = self.tokens.fingerprint(command.token)

        async with self.uow:
            reset = await self.uow.reset_tokens.get_by_fingerprint(fingerprint)
            if reset is None:
                raise InvalidResetToken()
            reset.ensure_usable(now=now)

            user = await self.uow.users.get(reset.user_id)
            if user is None:
                # 申請與點擊之間帳號被刪掉了
                raise InvalidResetToken()

            if not await self.uow.reset_tokens.mark_used(reset.id, used_at=now):
                raise InvalidResetToken()

            user.reset_password(new_password, hasher=self.hasher)
            await self.uow.users.save(user)
            await self.uow.commit()

        # 跨領域呼叫放在交易外
        await self.sessions.revoke_all(user.id)
