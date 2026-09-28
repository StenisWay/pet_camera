"""每個實作都必須明確繼承介面,而且沒有漏實作抽象方法。

介面新增方法時,這個測試會立刻指出哪些實作還沒跟上——包含測試替身。fake 落後於
正式實作是最難發現的一種 bug:application 的測試會全綠,上線才出錯。
"""

import inspect

import pytest

from app.core.rate_limit import RateLimitCounter
from app.core.redis_rate_limit import RedisRateLimitCounter
from app.core.system import SystemClock, Uuid7Generator
from app.domains.media.application.ports import (
    ClipWorker,
    DeviceDirectory,
    EventSource,
    FrameSource,
    MediaStorage,
    MediaUnitOfWork,
)
from app.domains.media.domain.repositories import MediaItemRepository
from app.domains.media.infrastructure.device_adapter import HttpDeviceDirectory
from app.domains.media.infrastructure.event_adapter import HttpEventSource
from app.domains.media.infrastructure.r2_storage import R2MediaStorage
from app.domains.media.infrastructure.repositories import SqlAlchemyMediaItemRepository
from app.domains.media.infrastructure.unit_of_work import SqlAlchemyMediaUnitOfWork
from app.domains.media.infrastructure.worker_adapter import HttpWorker
from app.shared_kernel.ports import Clock, IdGenerator
from tests.domains.media.fakes import (
    FakeClipWorker,
    FakeDeviceDirectory,
    FakeEventSource,
    FakeFrameSource,
    FakeMediaItemRepository,
    FakeMediaStorage,
    FakeMediaUnitOfWork,
    FakeRateLimitCounter,
    FixedClock,
    SequentialIds,
)

IMPLEMENTATIONS = [
    (MediaItemRepository, SqlAlchemyMediaItemRepository),
    (MediaItemRepository, FakeMediaItemRepository),
    (MediaUnitOfWork, SqlAlchemyMediaUnitOfWork),
    (MediaUnitOfWork, FakeMediaUnitOfWork),
    (DeviceDirectory, HttpDeviceDirectory),
    (DeviceDirectory, FakeDeviceDirectory),
    (EventSource, HttpEventSource),
    (EventSource, FakeEventSource),
    (FrameSource, HttpWorker),
    (FrameSource, FakeFrameSource),
    (ClipWorker, HttpWorker),
    (ClipWorker, FakeClipWorker),
    (MediaStorage, R2MediaStorage),
    (MediaStorage, FakeMediaStorage),
    (RateLimitCounter, RedisRateLimitCounter),
    (RateLimitCounter, FakeRateLimitCounter),
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
