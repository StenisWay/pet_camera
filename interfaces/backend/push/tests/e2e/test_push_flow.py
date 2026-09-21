"""端到端:手機登記 → 事件 ready → 推播送到手機;換帳號後改推給新帳號。

整支 app、真實資料庫、真實的兩個領域接線(notifications 經 push_tokens.api 取端點),
只有 Device 服務、Redis、R2、FCM 是 fake(不對外發網路)。
標記 integration,需要真實 PostgreSQL:uv run pytest -m integration
"""

import uuid
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    get_clock,
    get_id_generator,
    get_rate_limit_counter,
    get_session_factory_dep,
)
from app.core.security import get_current_user_id
from app.core.system import SystemClock, Uuid7Generator
from app.domains.notifications.application.ports import DeviceInfo
from app.domains.notifications.infrastructure.recipient_adapter import (
    PushTokensRecipientDirectory,
)
from app.domains.notifications.presentation.dependencies import (
    get_device_directory,
    get_notification_window,
    get_push_gateway,
    get_recipient_directory,
    get_thumbnail_links,
)
from app.domains.push_tokens.api import PushTokensApi
from app.main import create_app
from tests.domains.notifications.fakes import (
    FakeDeviceDirectory,
    FakeThumbnailLinks,
    InMemoryNotificationWindow,
    RecordingPushGateway,
)
from tests.fakes import InMemoryRateLimitCounter

pytestmark = pytest.mark.integration

ALICE = uuid.UUID("00000000-0000-0000-0000-00000000a11c")
BOB = uuid.UUID("00000000-0000-0000-0000-0000000000b0")
DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
INTERNAL = {"X-Internal-Api-Key": "change-me-internal"}


@pytest.fixture
def state():
    return {"user": ALICE}


@pytest.fixture
def devices() -> FakeDeviceDirectory:
    directory = FakeDeviceDirectory()
    directory.given(DeviceInfo(id=DEVICE, name="客廳", owner_id=ALICE))
    return directory


@pytest.fixture
def gateway() -> RecordingPushGateway:
    return RecordingPushGateway()


@pytest.fixture
def app(session_factory, state, devices, gateway):
    application = create_app(lifespan_enabled=False)
    recipients = PushTokensRecipientDirectory(PushTokensApi.from_session_factory(session_factory))
    window = InMemoryNotificationWindow()
    application.dependency_overrides.update(
        {
            get_settings: lambda: Settings(lookup_retry_delays_seconds=(0,)),
            get_session_factory_dep: lambda: session_factory,
            get_current_user_id: lambda: state["user"],
            get_clock: lambda: SystemClock(),
            get_id_generator: lambda: Uuid7Generator(),
            get_rate_limit_counter: lambda: InMemoryRateLimitCounter(),
            get_device_directory: lambda: devices,
            get_notification_window: lambda: window,
            get_recipient_directory: lambda: recipients,
            get_thumbnail_links: lambda: FakeThumbnailLinks(),
            get_push_gateway: lambda: gateway,
        }
    )
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://push.test") as c:
        yield c


def _event() -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "device_id": str(DEVICE),
        "confidence_score": 0.9,
        "thumbnail_object_key": None,
        "started_at": "2026-09-20T03:14:00Z",
    }


async def test_registered_phone_receives_the_owners_event(client, gateway):
    registered = await client.put("/push-tokens", json={"platform": "app", "token": "fcm-1"})
    assert registered.status_code == 200

    assert (
        await client.post("/internal/notifications/event-ready", json=_event(), headers=INTERNAL)
    ).status_code == 202

    assert [(r.token, n.title) for r, n in gateway.sent] == [("fcm-1", "客廳 偵測到活動")]


async def test_after_switching_accounts_the_previous_owner_no_longer_reaches_the_phone(
    client, state, devices, gateway
):
    """驗收:同一支手機以 B 帳號登入後,A 帳號的事件不再推播到該裝置。"""
    first = (await client.put("/push-tokens", json={"platform": "app", "token": "fcm-1"})).json()
    state["user"] = BOB
    second = (await client.put("/push-tokens", json={"platform": "app", "token": "fcm-1"})).json()
    assert second["id"] == first["id"]

    await client.post("/internal/notifications/event-ready", json=_event(), headers=INTERNAL)

    assert gateway.sent == []
    assert (await client.get("/push-tokens")).json()["items"][0]["id"] == first["id"]
