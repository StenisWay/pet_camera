"""每個實作都明確繼承介面,而且沒有漏實作抽象方法。

介面新增方法時,這個測試會立刻指出哪些實作還沒跟上——包含測試替身,
否則 fake 會默默落後於正式實作。
"""

import inspect

import pytest

from app.core.system import SystemClock, Uuid7Generator
from app.domains.detection.application.ports import (
    Backoff,
    ClipEncoder,
    DetectionUnitOfWork,
    FrameSource,
    MediaUploader,
    PushNotifier,
)
from app.domains.detection.domain.repositories import EventRepository
from app.domains.detection.infrastructure.backoff import ExponentialBackoff
from app.domains.detection.infrastructure.push_adapter import HttpPushNotifier
from app.domains.detection.infrastructure.repositories import SqlAlchemyEventRepository
from app.domains.detection.infrastructure.storage_adapter import R2MediaUploader
from app.domains.detection.infrastructure.unit_of_work import SqlAlchemyDetectionUnitOfWork
from app.domains.timeline.application.ports import (
    DeviceOwnership,
    MediaUrlIssuer,
    TimelineQueries,
    TimelineUnitOfWork,
)
from app.domains.timeline.domain.repositories import TimelineEventRepository
from app.domains.timeline.infrastructure.device_adapter import HttpDeviceOwnership
from app.domains.timeline.infrastructure.queries import SqlAlchemyTimelineQueries
from app.domains.timeline.infrastructure.repositories import (
    SqlAlchemyTimelineEventRepository,
)
from app.domains.timeline.infrastructure.storage_adapter import R2MediaUrlIssuer
from app.domains.timeline.infrastructure.unit_of_work import SqlAlchemyTimelineUnitOfWork
from app.shared_kernel.ports import Clock, IdGenerator
from tests.domains.detection.fakes import (
    FakeDetectionUnitOfWork,
    FakeEventRepository,
    FakeMediaUploader,
    FakePushNotifier,
    NoWaitBackoff,
)
from tests.domains.timeline.fakes import (
    FakeDeviceOwnership,
    FakeMediaUrlIssuer,
    FakeTimelineEventRepository,
    FakeTimelineQueries,
    FakeTimelineUnitOfWork,
)
from tests.fakes import FixedClock, SequentialIds

IMPLEMENTATIONS = [
    # detection
    (EventRepository, SqlAlchemyEventRepository),
    (EventRepository, FakeEventRepository),
    (DetectionUnitOfWork, SqlAlchemyDetectionUnitOfWork),
    (DetectionUnitOfWork, FakeDetectionUnitOfWork),
    (MediaUploader, R2MediaUploader),
    (MediaUploader, FakeMediaUploader),
    (PushNotifier, HttpPushNotifier),
    (PushNotifier, FakePushNotifier),
    (Backoff, ExponentialBackoff),
    (Backoff, NoWaitBackoff),
    # timeline
    (TimelineEventRepository, SqlAlchemyTimelineEventRepository),
    (TimelineEventRepository, FakeTimelineEventRepository),
    (TimelineUnitOfWork, SqlAlchemyTimelineUnitOfWork),
    (TimelineUnitOfWork, FakeTimelineUnitOfWork),
    (TimelineQueries, SqlAlchemyTimelineQueries),
    (TimelineQueries, FakeTimelineQueries),
    (DeviceOwnership, HttpDeviceOwnership),
    (DeviceOwnership, FakeDeviceOwnership),
    (MediaUrlIssuer, R2MediaUrlIssuer),
    (MediaUrlIssuer, FakeMediaUrlIssuer),
    # shared
    (Clock, SystemClock),
    (Clock, FixedClock),
    (IdGenerator, Uuid7Generator),
    (IdGenerator, SequentialIds),
]


@pytest.mark.parametrize(
    ("interface", "impl"), IMPLEMENTATIONS, ids=lambda x: x.__name__
)
def test_implementation_explicitly_implements_interface(interface, impl):
    assert issubclass(impl, interface), f"{impl.__name__} 沒有繼承 {interface.__name__}"
    assert not inspect.isabstract(impl), f"{impl.__name__} 尚未實作:{impl.__abstractmethods__}"


def test_frame_source_and_encoder_have_no_production_adapter_yet():
    """F2 的 RTSP 與 ffmpeg adapter 尚未實作(見 README 的已知限制)。

    這個測試不是在慶祝缺口,而是讓它顯性化:真的接上時這裡會紅,
    提醒把實作加進上面的 IMPLEMENTATIONS 一起檢查。
    """
    assert inspect.isabstract(FrameSource)
    assert inspect.isabstract(ClipEncoder)
