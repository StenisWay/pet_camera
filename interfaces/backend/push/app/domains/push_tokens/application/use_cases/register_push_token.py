from app.domains.push_tokens.application.dtos import PushTokenResult, RegisterPushTokenCommand
from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.domain.entities import PushToken
from app.shared_kernel.ports import Clock, IdGenerator


class RegisterPushToken:
    """PUT /push-tokens(09_spec 第 2.4 節):同一端點只有一筆,換帳號時改綁(審查 #4)。"""

    def __init__(self, uow: PushTokensUnitOfWork, ids: IdGenerator, clock: Clock) -> None:
        self.uow = uow
        self.ids = ids
        self.clock = clock

    async def execute(self, command: RegisterPushTokenCommand) -> PushTokenResult:
        async with self.uow:
            existing = await self.uow.tokens.find_by_endpoint(command.platform, command.token)
            if existing is None:
                registration = PushToken.register(
                    id=self.ids.new_id(),
                    user_id=command.user_id,
                    platform=command.platform,
                    token=command.token,
                    now=self.clock.now(),
                )
            else:
                registration = existing
                registration.rebind_to(command.user_id)
            stored = await self.uow.tokens.save(registration)
            await self.uow.commit()
        return PushTokenResult.from_entity(stored)
