"""合約測試的 uow fixture:同一份測試跑兩個實作。

這就是合約測試的全部意義——application 層用 fake 測出來的綠燈,要能代表
正式實作的行為。兩邊任何一點不一致,這裡就會紅。
"""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.domains.accounts.application.ports import AccountsUnitOfWork
from app.domains.accounts.infrastructure.orm import UserRow
from app.domains.accounts.infrastructure.unit_of_work import SqlAlchemyAccountsUnitOfWork
from tests.database import TEST_DATABASE_URL, postgres_session_factory
from tests.domains.accounts.fakes import FakeAccountsUnitOfWork

# password_reset_tokens.user_id 有外鍵,真實資料庫需要一個存在的對象
OWNER_ID = uuid.UUID("01931f00-0000-7000-8000-000000000001")


@pytest.fixture
def owner_id() -> uuid.UUID:
    return OWNER_ID


@pytest.fixture(params=["fake", "sqlalchemy"])
async def uow(request: pytest.FixtureRequest) -> AsyncIterator[AccountsUnitOfWork]:
    if request.param == "fake":
        yield FakeAccountsUnitOfWork()
        return

    if not TEST_DATABASE_URL:
        pytest.skip("需要 AUTH_TEST_DATABASE_URL 才能跑 SQLAlchemy 這一半的合約")

    async with postgres_session_factory() as session_factory:
        async with session_factory() as session:
            session.add(
                UserRow(
                    id=OWNER_ID,
                    email="fixture-owner@example.com",
                    password_hash=None,
                    failed_login_attempts=0,
                    locked_until=None,
                )
            )
            await session.commit()
        yield SqlAlchemyAccountsUnitOfWork(session_factory)
