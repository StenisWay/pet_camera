"""push_tokens 對其他領域公開的唯一入口。

notifications 發送時需要「某使用者的所有端點(含 token)」與「刪除失效端點」;
它只能透過這裡取得,而且只在自己的 infrastructure adapter 中呼叫。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.infrastructure.unit_of_work import SqlAlchemyPushTokensUnitOfWork


@dataclass(frozen=True)
class PushEndpoint:
    id: uuid.UUID
    platform: str  # "app" / "web"
    token: str


class PushTokensApi:
    def __init__(self, uow_factory: Callable[[], PushTokensUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    @classmethod
    def from_session_factory(
        cls, session_factory: async_sessionmaker[AsyncSession]
    ) -> PushTokensApi:
        return cls(lambda: SqlAlchemyPushTokensUnitOfWork(session_factory))

    async def list_endpoints(self, user_id: uuid.UUID) -> list[PushEndpoint]:
        async with self._uow_factory() as uow:
            registrations = await uow.tokens.list_by_user(user_id)
        return [PushEndpoint(r.id, r.platform.value, r.token) for r in registrations]

    async def remove(self, push_token_id: uuid.UUID) -> None:
        """PUSH_003:推播服務回報端點失效時呼叫;不存在時不視為錯誤。"""
        async with self._uow_factory() as uow:
            await uow.tokens.delete(push_token_id)
            await uow.commit()
