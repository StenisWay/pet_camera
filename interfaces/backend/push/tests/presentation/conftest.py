"""HTTP 層測試:用真的 app,但每個 port 都 override 成 fake——不連資料庫、Redis、R2、FCM。"""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.dependencies import get_clock, get_id_generator, get_rate_limit_counter
from app.core.security import get_current_user_id
from app.domains.notifications.presentation.dependencies import (
    get_device_directory,
    get_notification_window,
    get_push_gateway,
    get_recipient_directory,
    get_thumbnail_links,
)
from app.domains.push_tokens.presentation.dependencies import get_push_tokens_uow
from app.main import create_app
from tests.domains.notifications.fakes import (
    FakeDeviceDirectory,
    FakeRecipientDirectory,
    FakeThumbnailLinks,
    InMemoryNotificationWindow,
    RecordingPushGateway,
)
from tests.domains.push_tokens.builders import ALICE
from tests.domains.push_tokens.fakes import FakePushTokensUnitOfWork
from tests.fakes import FixedClock, InMemoryRateLimitCounter, SequentialIds

INTERNAL_KEY = "change-me-internal"


@pytest.fixture
def current_user_id() -> uuid.UUID:
    return ALICE


@pytest.fixture
def uow() -> FakePushTokensUnitOfWork:
    return FakePushTokensUnitOfWork()


@pytest.fixture
def rate_limit_counter() -> InMemoryRateLimitCounter:
    return InMemoryRateLimitCounter()


@pytest.fixture
def devices() -> FakeDeviceDirectory:
    return FakeDeviceDirectory()


@pytest.fixture
def recipients() -> FakeRecipientDirectory:
    return FakeRecipientDirectory()


@pytest.fixture
def gateway() -> RecordingPushGateway:
    return RecordingPushGateway()


@pytest.fixture
def app(uow, rate_limit_counter, devices, recipients, gateway, current_user_id):
    application = create_app(lifespan_enabled=False)
    window = InMemoryNotificationWindow()
    thumbnails = FakeThumbnailLinks()
    application.dependency_overrides.update(
        {
            get_settings: lambda: Settings(lookup_retry_delays_seconds=(0, 0)),
            get_current_user_id: lambda: current_user_id,
            get_clock: lambda: FixedClock(),
            get_id_generator: lambda: SequentialIds(),
            get_rate_limit_counter: lambda: rate_limit_counter,
            get_push_tokens_uow: lambda: uow,
            get_device_directory: lambda: devices,
            get_notification_window: lambda: window,
            get_recipient_directory: lambda: recipients,
            get_thumbnail_links: lambda: thumbnails,
            get_push_gateway: lambda: gateway,
        }
    )
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://push.test"
    ) as http_client:
        yield http_client
