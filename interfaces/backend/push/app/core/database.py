"""資料庫連線與 Declarative Base。

命名規則、timestamptz 對應、TimestampMixin 依 postgres-db-master 的規範。
Push 只擁有 push_tokens 一張表(13_ADR 第 1 節);schema 的正本在共用的 db/migrations/。

目前不連線任何真實資料庫:engine 是 lazy 的,import 本模組不會建立連線。
"""

from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # 01_資料模型與儲存規格.md 第 2.0 節:時間一律 timestamptz,以 UTC 儲存
    type_annotation_map = {datetime: DateTime(timezone=True)}


class TimestampMixin:
    """第 2.0 節:每張表都有 created_at、updated_at,updated_at 由資料庫維護。"""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)
