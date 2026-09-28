"""DevicesUnitOfWork 的 SQLAlchemy 實作。"""

from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.devices.application.ports import DevicesUnitOfWork
from app.domains.devices.infrastructure.repositories import SqlAlchemyDeviceRepository


class SqlAlchemyDevicesUnitOfWork(DevicesUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.devices = SqlAlchemyDeviceRepository(self.session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        # 已 commit 時是 no-op;沒 commit 就離開一律回滾
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
