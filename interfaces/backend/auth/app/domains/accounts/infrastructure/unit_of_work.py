"""accounts 的 UnitOfWork 實作。

交易邊界由 use case 的 `async with uow:` 決定,**必須明確 commit**——
未 commit 就離開一律回滾,忘記 commit 會在測試中立刻被抓到,而不是默默寫入一半。
"""

from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.accounts.application.ports import AccountsUnitOfWork
from app.domains.accounts.infrastructure.repositories import (
    SqlAlchemyPasswordResetTokenRepository,
    SqlAlchemyUserRepository,
)


class SqlAlchemyAccountsUnitOfWork(AccountsUnitOfWork):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> Self:
        self.session = self._session_factory()
        self.users = SqlAlchemyUserRepository(self.session)
        self.reset_tokens = SqlAlchemyPasswordResetTokenRepository(self.session)
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        # 已 commit 時是 no-op;沒 commit 的話這行就是回滾
        await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()
