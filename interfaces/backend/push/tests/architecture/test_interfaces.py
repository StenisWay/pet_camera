"""每個介面至少要有正式實作與測試替身,且都能被實例化(沒有漏實作的抽象方法)。"""

import inspect

import pytest

from app.core.rate_limit import RateLimitCounter
from app.core.redis_rate_limit import RedisRateLimitCounter
from app.core.system import SystemClock, Uuid7Generator
from app.domains.notifications.application.ports import (
    DeviceDirectory,
    NotificationWindow,
    PushGateway,
    RecipientDirectory,
    ThumbnailLinks,
)
from app.domains.notifications.infrastructure.device_directory import HttpDeviceDirectory
from app.domains.notifications.infrastructure.gateways import (
    FcmGateway,
    RoutingPushGateway,
    UnconfiguredGateway,
    WebPushGateway,
)
from app.domains.notifications.infrastructure.r2_thumbnails import R2ThumbnailLinks
from app.domains.notifications.infrastructure.recipient_adapter import (
    PushTokensRecipientDirectory,
)
from app.domains.notifications.infrastructure.redis_window import RedisNotificationWindow
from app.domains.push_tokens.application.ports import PushTokensUnitOfWork
from app.domains.push_tokens.domain.repositories import PushTokenRepository
from app.domains.push_tokens.infrastructure.repositories import SqlAlchemyPushTokenRepository
from app.domains.push_tokens.infrastructure.unit_of_work import SqlAlchemyPushTokensUnitOfWork
from app.shared_kernel.ports import Clock, IdGenerator
from tests.domains.notifications.fakes import (
    FakeDeviceDirectory,
    FakeRecipientDirectory,
    FakeThumbnailLinks,
    InMemoryNotificationWindow,
    RecordingPushGateway,
)
from tests.domains.push_tokens.fakes import FakePushTokenRepository, FakePushTokensUnitOfWork
from tests.fakes import FixedClock, InMemoryRateLimitCounter, SequentialIds

IMPLEMENTATIONS = [
    (PushTokenRepository, SqlAlchemyPushTokenRepository),
    (PushTokenRepository, FakePushTokenRepository),
    (PushTokensUnitOfWork, SqlAlchemyPushTokensUnitOfWork),
    (PushTokensUnitOfWork, FakePushTokensUnitOfWork),
    (DeviceDirectory, HttpDeviceDirectory),
    (DeviceDirectory, FakeDeviceDirectory),
    (NotificationWindow, RedisNotificationWindow),
    (NotificationWindow, InMemoryNotificationWindow),
    (RecipientDirectory, PushTokensRecipientDirectory),
    (RecipientDirectory, FakeRecipientDirectory),
    (ThumbnailLinks, R2ThumbnailLinks),
    (ThumbnailLinks, FakeThumbnailLinks),
    (PushGateway, FcmGateway),
    (PushGateway, WebPushGateway),
    (PushGateway, RoutingPushGateway),
    (PushGateway, UnconfiguredGateway),
    (PushGateway, RecordingPushGateway),
    (RateLimitCounter, RedisRateLimitCounter),
    (RateLimitCounter, InMemoryRateLimitCounter),
    (Clock, SystemClock),
    (Clock, FixedClock),
    (IdGenerator, Uuid7Generator),
    (IdGenerator, SequentialIds),
]


@pytest.mark.parametrize(("interface", "impl"), IMPLEMENTATIONS, ids=lambda x: x.__name__)
def test_implementation_explicitly_implements_interface(interface, impl):
    assert issubclass(impl, interface)
    assert not inspect.isabstract(impl), f"{impl.__name__} 尚未實作:{impl.__abstractmethods__}"
