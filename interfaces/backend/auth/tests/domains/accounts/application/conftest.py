"""application 測試共用的組裝。

這一層完全不碰資料庫:所有外部依賴都是 fake,紅綠循環因此是毫秒等級。
"""

from datetime import UTC, datetime

import pytest

from tests.domains.accounts.fakes import (
    FakeAccountPurger,
    FakeAccountsUnitOfWork,
    FakeEmailSender,
    FakeLoginAttemptTracker,
    FakePasswordHasher,
    FakePasswordResetThrottle,
    FakeSessionService,
    FakeTokenFactory,
    FixedClock,
    SequentialIdGenerator,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def uow() -> FakeAccountsUnitOfWork:
    return FakeAccountsUnitOfWork()


@pytest.fixture
def hasher() -> FakePasswordHasher:
    return FakePasswordHasher()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def ids() -> SequentialIdGenerator:
    return SequentialIdGenerator()


@pytest.fixture
def tokens() -> FakeTokenFactory:
    return FakeTokenFactory()


@pytest.fixture
def sessions() -> FakeSessionService:
    return FakeSessionService()


@pytest.fixture
def attempts() -> FakeLoginAttemptTracker:
    return FakeLoginAttemptTracker()


@pytest.fixture
def throttle() -> FakePasswordResetThrottle:
    return FakePasswordResetThrottle()


@pytest.fixture
def mailer() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture
def device_purger() -> FakeAccountPurger:
    return FakeAccountPurger("device")


@pytest.fixture
def album_purger() -> FakeAccountPurger:
    return FakeAccountPurger("album")
