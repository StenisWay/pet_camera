from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.infrastructure.repositories import SqlAlchemyPushTokenRepository


class SqlAlchemyPushTokensUnitOfWork(PushTokensUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.tokens = SqlAlchemyPushTokenRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.session.rollback()  # 已 commit 時為 no-op
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
