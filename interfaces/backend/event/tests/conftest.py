"""需要真實資料庫的測試才會用到這裡的 fixture。

**不用 SQLite 代替 PostgreSQL**:CHECK 約束、timestamptz、numeric 精度、列組比較
(cursor 分頁靠它)的行為都不一樣,用 SQLite 會讓真正的錯誤溜過去。

預設不執行(pyproject 的 addopts = -m 'not integration'),要跑:
    uv run pytest -m integration        # 需要 TEST_DATABASE_URL 或可用的 Docker
"""

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import orm  # noqa: F401 — 讓 EventRow 掛上 Base.metadata
from app.core.database import Base


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """優先用 CI 的 service container;否則臨時起一個 testcontainer。"""
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """container 是 session scope(只啟動一次),engine 是 function scope——
    session scope 的 async fixture 需要同範圍的事件迴圈,這樣切可以避開那個問題。"""
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
