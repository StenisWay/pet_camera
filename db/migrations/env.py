"""Alembic 環境設定。

連線字串一律從環境變數 DATABASE_URL_MIGRATE 取得(不進版控),
且必須使用 migration 專用帳號(可改 schema),不是服務用的應用程式帳號。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL_MIGRATE")
    if not url:
        raise RuntimeError(
            "未設定 DATABASE_URL_MIGRATE。請複製 db/.env.example 為 db/.env 後 "
            "`set -a; . ./.env; set +a`,或直接 export 該變數。"
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # 拿不到鎖就早點失敗,不要卡住其他連線(正式環境尤其重要)
        connection.exec_driver_sql("set lock_timeout = '5s'")
        connection.exec_driver_sql("set statement_timeout = '300s'")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
