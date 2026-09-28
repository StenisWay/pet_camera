"""application 層測試共用的裝配。全部用 fake,不碰 Redis / TURN / Device 服務。"""

from datetime import timedelta

import pytest

from tests.domains.streaming.builders import NOW, a_device
from tests.domains.streaming.fakes import (
    FakeClock,
    FakeDeviceDirectory,
    FakeSignalingEvents,
    FakeTurnCredentialIssuer,
    InMemoryStreamSessionRepository,
)

ANSWER_TIMEOUT = timedelta(seconds=5)
# 測試裡的「逾時」用極短的時間,行為一樣但不讓測試真的等 5 秒
FAST_TIMEOUT = timedelta(milliseconds=20)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def sessions(clock: FakeClock) -> InMemoryStreamSessionRepository:
    return InMemoryStreamSessionRepository(clock)


@pytest.fixture
def events() -> FakeSignalingEvents:
    return FakeSignalingEvents()


@pytest.fixture
def devices() -> FakeDeviceDirectory:
    return FakeDeviceDirectory(a_device())


@pytest.fixture
def turn() -> FakeTurnCredentialIssuer:
    return FakeTurnCredentialIssuer()
