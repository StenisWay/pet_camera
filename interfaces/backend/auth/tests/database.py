"""infrastructure 測試用的真實 PostgreSQL 連線。

**刻意不用 SQLite 代替**。這一層要驗的正是 PostgreSQL 特有的行為:
`CHECK email = lower(email)`、`ON DELETE CASCADE`、`timestamptz` 的時區還原、
部分索引、以及條件 UPDATE 的 rowcount。SQLite 對這些的語意不同,綠燈沒有意義。

沒設 AUTH_TEST_DATABASE_URL 時整組跳過,fake 那一半照常跑:

    AUTH_TEST_DATABASE_URL=postgresql+asyncpg://user:pw@localhost/pet_camera_test \\
        uv run pytest

指向的資料庫會被建表與刪表,**不要指到有資料的庫**。
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.orm_models import Base

TEST_DATABASE_URL = os.getenv("AUTH_TEST_DATABASE_URL", "")

requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="需要 AUTH_TEST_DATABASE_URL 指向一個可建表的 PostgreSQL",
)


@asynccontextmanager
async def postgres_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """每個測試自己的乾淨 schema:建表 → 跑測試 → 刪表。"""
    engine = create_async_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
    finally:
        await engine.dispose()
