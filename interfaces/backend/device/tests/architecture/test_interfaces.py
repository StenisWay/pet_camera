"""每個實作都必須**明確繼承**它的介面,而且沒有漏實作抽象方法。

用 ABC 而不是 Protocol 的好處就在這裡:實作關係寫在類別宣告上,漏方法時建立實例
當下就 TypeError。介面日後新增方法時,這個測試會立刻指出哪些實作還沒跟上。
"""

import inspect

import pytest

from app.core.rate_limit import RateLimitCounter
from app.core.system import SystemClock, Uuid7Generator
from app.domains.devices.application.ports import (
    DeviceSecrets,
    DevicesUnitOfWork,
    EventCleanup,
    PairingCodeFactory,
)
from app.domains.devices.domain.repositories import DeviceRepository
from app.domains.devices.infrastructure.event_cleanup import HttpEventCleanup
from app.domains.devices.infrastructure.repositories import SqlAlchemyDeviceRepository
from app.domains.devices.infrastructure.security import (
    RandomPairingCodeFactory,
    Sha256DeviceSecrets,
)
from app.domains.devices.infrastructure.unit_of_work import SqlAlchemyDevicesUnitOfWork
from app.shared_kernel.ports import Clock, IdGenerator
from tests.domains.devices.fakes import (
    FakeDeviceRepository,
    FakeDeviceSecrets,
    FakeDevicesUnitOfWork,
    FakeEventCleanup,
    FixedClock,
    SequentialIds,
    StubPairingCodeFactory,
)

IMPLEMENTATIONS = [
    (DeviceRepository, SqlAlchemyDeviceRepository),
    (DeviceRepository, FakeDeviceRepository),
    (DevicesUnitOfWork, SqlAlchemyDevicesUnitOfWork),
    (DevicesUnitOfWork, FakeDevicesUnitOfWork),
    (EventCleanup, HttpEventCleanup),
    (EventCleanup, FakeEventCleanup),
    (DeviceSecrets, Sha256DeviceSecrets),
    (DeviceSecrets, FakeDeviceSecrets),
    (PairingCodeFactory, RandomPairingCodeFactory),
    (PairingCodeFactory, StubPairingCodeFactory),
    (Clock, SystemClock),
    (Clock, FixedClock),
    (IdGenerator, Uuid7Generator),
    (IdGenerator, SequentialIds),
]


@pytest.mark.parametrize(
    ("interface", "impl"), IMPLEMENTATIONS, ids=lambda x: x.__name__
)
def test_implementation_explicitly_implements_interface(interface, impl):
    assert issubclass(impl, interface)
    assert not inspect.isabstract(impl), f"{impl.__name__} 尚未實作:{impl.__abstractmethods__}"


def test_rate_limit_counter_is_still_an_interface_without_implementations():
    """限流計數器的 Redis 實作尚未接上,見 README 已知限制。

    這個測試是刻意留的提醒:接上之後把它換成上面 IMPLEMENTATIONS 的一列。
    """
    assert inspect.isabstract(RateLimitCounter)
