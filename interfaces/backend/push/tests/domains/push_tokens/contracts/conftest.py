"""合約測試:同一份測試跑在所有 PushTokenRepository / PushTokensUnitOfWork 實作上。

- fake 通過 → application 測試使用的替身行為與正式實作一致,那些測試才可信
- SQLAlchemy 通過 → 正式實作確實遵守介面的 docstring 承諾(需要真實 PostgreSQL)
"""

from collections.abc import Callable
from dataclasses import dataclass

import pytest

from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from tests.domains.push_tokens.fakes import FakePushTokensUnitOfWork


@dataclass
class Store:
    uow: Callable[[], PushTokensUnitOfWork]


@pytest.fixture(params=["fake", pytest.param("sqlalchemy", marks=pytest.mark.integration)])
def store(request) -> Store:
    if request.param == "fake":
        shared = FakePushTokensUnitOfWork()
        return Store(uow=lambda: shared)  # 同一個實例 = 同一個「資料庫」
    from app.domains.push_tokens.infrastructure.unit_of_work import (
        SqlAlchemyPushTokensUnitOfWork,
    )

    session_factory = request.getfixturevalue("session_factory")
    return Store(uow=lambda: SqlAlchemyPushTokensUnitOfWork(session_factory))
