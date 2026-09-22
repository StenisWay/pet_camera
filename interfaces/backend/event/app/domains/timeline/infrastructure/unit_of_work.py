"""TimelineUnitOfWork 的 SQLAlchemy 實作。"""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.timeline.application.ports import TimelineUnitOfWork
from app.domains.timeline.infrastructure.repositories import (
    SqlAlchemyTimelineEventRepository,
)


class SqlAlchemyTimelineUnitOfWork(TimelineUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.events = SqlAlchemyTimelineEventRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.session.rollback()  # 已 commit 時是 no-op
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
