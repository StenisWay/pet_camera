"""MediaUnitOfWork 的 SQLAlchemy 實作。

交易邊界由 use case 用 `async with uow:` 決定;未 commit 就離開一律回滾——
忘記 commit 會在合約測試中立刻被抓到,而不是默默寫入一半。

ADR 第 4 節:Media 的寫入選一致性(C)。連不到 VM-3 的 Postgres 時,這裡會拋出
連線例外,由 core/http_errors.py 轉成 SRV_002,而不是憑空先回成功。
"""

from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.media.application.ports import MediaUnitOfWork
from app.domains.media.infrastructure.repositories import SqlAlchemyMediaItemRepository


class SqlAlchemyMediaUnitOfWork(MediaUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.media = SqlAlchemyMediaItemRepository(self.session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.session.rollback()  # 已 commit 時為 no-op
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
