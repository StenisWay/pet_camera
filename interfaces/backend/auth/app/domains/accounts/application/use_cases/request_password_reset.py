"""忘記密碼:寄出一次性重設連結(02_spec 第 2.4 節)。

本 use case 的每一條分支都必須讓呼叫端看起來一模一樣:

- email 沒註冊 → 什麼都不做,照樣回成功。
- 寄信失敗 → 記 log,照樣回成功。

任何一處回不同的東西,這個端點就成了帳號列舉器——而那正是「一律回相同成功訊息」
要防的事。唯一會回錯誤的情況是輸入本身不合法(VAL_001)或超過限流(RATE_001),
兩者都與「這個 email 存不存在」無關。
"""

import logging

from app.domains.accounts.application.dtos import RequestPasswordResetCommand
from app.domains.accounts.application.ports import (
    AccountsUnitOfWork,
    EmailSender,
    PasswordResetThrottle,
)
from app.domains.accounts.domain.entities import PasswordResetToken
from app.domains.accounts.domain.value_objects import Email
from app.shared_kernel.ports import Clock, IdGenerator, OpaqueTokenFactory

logger = logging.getLogger(__name__)


class RequestPasswordReset:
    def __init__(
        self,
        uow: AccountsUnitOfWork,
        *,
        clock: Clock,
        ids: IdGenerator,
        tokens: OpaqueTokenFactory,
        mailer: EmailSender,
        throttle: PasswordResetThrottle,
        reset_url_template: str,
    ) -> None:
        self.uow = uow
        self.clock = clock
        self.ids = ids
        self.tokens = tokens
        self.mailer = mailer
        self.throttle = throttle
        self.reset_url_template = reset_url_template

    async def execute(self, command: RequestPasswordResetCommand) -> None:
        email = Email.parse(command.email)
        await self.throttle.check(email.value, command.client_ip)

        async with self.uow:
            user = await self.uow.users.get_by_email(email)
            if user is None:
                # 不存在:不建 token、不寄信、不回錯誤
                return

            secret = self.tokens.generate()
            await self.uow.reset_tokens.add(
                PasswordResetToken.issue(
                    id=self.ids.new_id(),
                    user_id=user.id,
                    token_hash=self.tokens.fingerprint(secret),
                    now=self.clock.now(),
                )
            )
            await self.uow.commit()

        # 寄信在交易外:SMTP 慢或掛掉都不該把資料庫交易拖著
        try:
            await self.mailer.send_password_reset(
                email.value, reset_url=self.reset_url_template.format(token=secret)
            )
        except Exception:
            # 對外仍回成功,但這是要告警的:使用者收不到信而我們毫無所覺
            logger.exception("password reset mail failed for a registered address")
