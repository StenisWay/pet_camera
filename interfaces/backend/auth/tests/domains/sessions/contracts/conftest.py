"""sessions 合約測試的 uow fixture:fake 與 SQLAlchemy 各跑一次。"""

import uuid
from collections.abc import AsyncIterator

import pytest

from app.domains.accounts.infrastructure.orm import UserRow
from app.domains.sessions.application.ports import SessionsUnitOfWork
from app.domains.sessions.infrastructure.unit_of_work import SqlAlchemySessionsUnitOfWork
from tests.database import TEST_DATABASE_URL, postgres_session_factory
from tests.domains.sessions.fakes import FakeSessionsUnitOfWork

# refresh_tokens.user_id 有外鍵(ON DELETE CASCADE),真實資料庫需要存在的對象
OWNER_ID = uuid.UUID("01931f00-0000-7000-8000-000000000011")
OTHER_ID = uuid.UUID("01931f00-0000-7000-8000-000000000012")


@pytest.fixture
def owner_id() -> uuid.UUID:
    return OWNER_ID


@pytest.fixture
def other_id() -> uuid.UUID:
    return OTHER_ID


@pytest.fixture(params=["fake", "sqlalchemy"])
async def uow(request: pytest.FixtureRequest) -> AsyncIterator[SessionsUnitOfWork]:
    if request.param == "fake":
        yield FakeSessionsUnitOfWork()
        return

    if not TEST_DATABASE_URL:
        pytest.skip("需要 AUTH_TEST_DATABASE_URL 才能跑 SQLAlchemy 這一半的合約")

    async with postgres_session_factory() as session_factory:
        async with session_factory() as session:
            for index, user_id in enumerate((OWNER_ID, OTHER_ID)):
                session.add(
                    UserRow(
                        id=user_id,
                        email=f"fixture-session-{index}@example.com",
                        password_hash=None,
                        failed_login_attempts=0,
                        locked_until=None,
                    )
                )
            await session.commit()
        yield SqlAlchemySessionsUnitOfWork(session_factory)
