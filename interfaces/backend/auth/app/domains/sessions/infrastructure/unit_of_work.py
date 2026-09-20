"""sessions 的 UnitOfWork 實作。"""

from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.sessions.application.ports import SessionsUnitOfWork
from app.domains.sessions.infrastructure.repositories import (
    SqlAlchemyRefreshTokenRepository,
)


class SqlAlchemySessionsUnitOfWork(SessionsUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.refresh_tokens = SqlAlchemyRefreshTokenRepository(self.session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
