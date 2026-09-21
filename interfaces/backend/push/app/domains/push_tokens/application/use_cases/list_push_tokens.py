import uuid

from app.domains.push_tokens.application.dtos import PushTokenResult
from app.domains.push_tokens.application.ports import PushTokensUnitOfWork


class ListPushTokens:
    """GET /push-tokens:設定頁還原通知開關狀態(審查 #11)。"""

    def __init__(self, uow: PushTokensUnitOfWork) -> None:
        self.uow = uow

    async def execute(self, user_id: uuid.UUID) -> list[PushTokenResult]:
        async with self.uow:
            registrations = await self.uow.tokens.list_by_user(user_id)
        return [PushTokenResult.from_entity(r) for r in registrations]
