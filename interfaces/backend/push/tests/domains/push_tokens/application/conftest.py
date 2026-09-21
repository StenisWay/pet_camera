import pytest

from tests.domains.push_tokens.fakes import FakePushTokensUnitOfWork
from tests.fakes import FixedClock, SequentialIds


@pytest.fixture
def uow() -> FakePushTokensUnitOfWork:
    return FakePushTokensUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()
