from datetime import UTC, datetime

import pytest

from tests.domains.accounts.fakes import FakeTokenFactory, FixedClock, SequentialIdGenerator
from tests.domains.sessions.fakes import FakeAccessTokenSigner, FakeSessionsUnitOfWork

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def uow() -> FakeSessionsUnitOfWork:
    return FakeSessionsUnitOfWork()


@pytest.fixture
def signer() -> FakeAccessTokenSigner:
    return FakeAccessTokenSigner()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def ids() -> SequentialIdGenerator:
    return SequentialIdGenerator()


@pytest.fixture
def tokens() -> FakeTokenFactory:
    return FakeTokenFactory()
