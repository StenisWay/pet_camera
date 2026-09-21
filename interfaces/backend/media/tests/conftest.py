"""整合測試用的資料庫 fixture。

**不用 SQLite 代替 PostgreSQL**:CHECK 約束、timestamptz、部分索引的行為都不同,
SQLite 會讓錯誤溜過去。

目前專案還沒建資料庫(見 README「待辦:建立資料庫」),所以這些 fixture 只有在
`pytest -m integration` 時才會被取用,預設的開發迴圈完全不需要 Docker 或 Postgres。
"""

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """優先用 TEST_DATABASE_URL(CI 的 service container),否則起 testcontainers。"""
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
async def engine(database_url: str):
    """container 是 session scope(只啟動一次),engine 是 function scope——

    避開 session scope 的 async fixture 與事件迴圈範圍不合的問題。
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.database import Base
    from app.orm_models import MediaItemRow  # noqa: F401  註冊 metadata

    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def session_factory(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(engine, expire_on_commit=False)
