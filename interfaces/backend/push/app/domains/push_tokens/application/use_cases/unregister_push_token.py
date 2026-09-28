import uuid

from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.domain.exceptions import PushTokenNotFound


class UnregisterPushToken:
    """DELETE /push-tokens/{id}:使用者關閉通知或登出時解除登記。"""

    def __init__(self, uow: PushTokensUnitOfWork) -> None:
        self.uow = uow

    async def execute(self, push_token_id: uuid.UUID, requester_id: uuid.UUID) -> None:
        async with self.uow:
            registration = await self.uow.tokens.get(push_token_id)
            # 不存在與非本人回相同錯誤,避免洩漏其他使用者的登記是否存在(審查 #5)
            if registration is None or not registration.is_owned_by(requester_id):
                raise PushTokenNotFound()
            await self.uow.tokens.delete(registration.id)
            await self.uow.commit()
