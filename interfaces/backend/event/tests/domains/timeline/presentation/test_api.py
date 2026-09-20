"""時間軸 API 的 HTTP 契約:08_spec 第 3、7 節。

這一層只驗證「規則有沒有正確接上 HTTP」——狀態碼、錯誤碼、回應欄位、權限。
業務規則本身已經在 domain 與 application 窮盡過,不在這裡重測。
"""

import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user_id
from app.domains.timeline.domain.entities import EventStatus
from app.domains.timeline.presentation.dependencies import (
    get_device_ownership,
    get_media_urls,
    get_timeline_queries,
    get_timeline_uow,
)
from app.main import create_app
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.timeline.builders import (
    ALICE,
    BOB,
    DEVICE,
    EVENT,
    STARTED,
    a_timeline_event,
    days,
)
from tests.domains.timeline.fakes import (
    FakeDeviceOwnership,
    FakeMediaUrlIssuer,
    FakeTimelineQueries,
    FakeTimelineUnitOfWork,
)
from tests.fakes import FixedClock

NOW = STARTED + timedelta(hours=1)


@pytest.fixture
def store() -> dict:
    return {}


@pytest.fixture
def uow(store) -> FakeTimelineUnitOfWork:
    return FakeTimelineUnitOfWork(store)


@pytest.fixture
def queries() -> FakeTimelineQueries:
    return FakeTimelineQueries()


@pytest.fixture
def ownership() -> FakeDeviceOwnership:
    return FakeDeviceOwnership({DEVICE: ALICE})


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(NOW)


@pytest.fixture
def app(uow, queries, ownership, clock):
    from app.core.system import get_clock

    app = create_app()
    app.dependency_overrides.update(
        {
            get_timeline_uow: lambda: uow,
            get_timeline_queries: lambda: queries,
            get_device_ownership: lambda: ownership,
            get_media_urls: FakeMediaUrlIssuer,
            get_clock: lambda: clock,
            get_current_user_id: lambda: ALICE,
        }
    )
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- 列表 ---------------------------------------------------------------


async def test_listing_events_returns_unix_timestamps(client, queries):
    """時間欄位一律 Unix timestamp(秒,整數),不是 ISO 字串。"""
    event = a_timeline_event()
    queries.given(event)

    resp = await client.get(f"/devices/{DEVICE}/events")

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["started_at"] == int(STARTED.timestamp())
    assert item["ended_at"] == int(event.ended_at.timestamp())
    assert isinstance(item["started_at"], int)


async def test_list_response_shape(client, queries):
    queries.given(a_timeline_event())

    item = (await client.get(f"/devices/{DEVICE}/events")).json()["items"][0]

    assert set(item) == {
        "id",
        "status",
        "confidence_score",
        "started_at",
        "ended_at",
        "duration_sec",
        "is_read",
        "is_partial",
        "thumbnail_url",
    }
    # device_id 已經在路徑上,不必在每一筆再回一次;object key 是內部細節,不外流
    assert "video_object_key" not in item
    assert "device_id" not in item


async def test_empty_timeline_is_an_empty_list_not_an_error(client):
    resp = await client.get(f"/devices/{DEVICE}/events")

    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}


async def test_next_cursor_is_returned_for_paging(client, queries):
    for i in range(1, 4):
        queries.given(a_timeline_event(id=uuid.UUID(int=i)))

    resp = await client.get(f"/devices/{DEVICE}/events", params={"limit": 2})

    assert resp.json()["next_cursor"] is not None


async def test_someone_elses_device_is_a_404_with_device_005(client, ownership):
    """規格審查 #2:非本人回 404 DEVICE_005,不是 403。"""
    ownership.owners = {DEVICE: BOB}

    resp = await client.get(f"/devices/{DEVICE}/events")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVICE_005"


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"cursor": "tampered!!"},
        {"date": "2026-13-01"},
        {"date": "2026-09-20", "from": 1758337200},
    ],
)
async def test_bad_query_parameters_are_val_001(client, params):
    resp = await client.get(f"/devices/{DEVICE}/events", params=params)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAL_001"


async def test_database_outage_is_503_not_an_empty_list(client, queries):
    """13_ADR 第 4 節:讀取選一致性,不可回空列表讓使用者以為沒有事件。"""
    queries.unavailable = ServiceUnavailable()

    resp = await client.get(f"/devices/{DEVICE}/events")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SRV_002"


async def test_listing_requires_authentication(app, queries):
    app.dependency_overrides.pop(get_current_user_id)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.get(f"/devices/{DEVICE}/events")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_001"


# --- 播放 ---------------------------------------------------------------


async def test_playback_url_is_returned_for_a_ready_event(client, uow):
    event = uow.given(a_timeline_event())

    resp = await client.get(f"/events/{EVENT}/playback-url")

    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://r2.example.com/")
    assert resp.json()["expires_in"] == 600
    assert event.video_object_key in resp.json()["url"]


@pytest.mark.parametrize(
    ("status", "expected_status", "expected_code"),
    [
        (EventStatus.PROCESSING, 409, "TIMELINE_005"),
        (EventStatus.FAILED, 409, "EVENT_001"),
    ],
)
async def test_unplayable_events_map_to_their_error_codes(
    client, uow, status, expected_status, expected_code
):
    uow.given(a_timeline_event(status=status))

    resp = await client.get(f"/events/{EVENT}/playback-url")

    assert resp.status_code == expected_status
    assert resp.json()["error"]["code"] == expected_code


async def test_expired_video_is_410_timeline_002(client, uow, clock):
    uow.given(a_timeline_event())
    clock.set(STARTED + days(8))

    resp = await client.get(f"/events/{EVENT}/playback-url")

    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "TIMELINE_002"


async def test_unknown_event_playback_is_404(client):
    resp = await client.get(f"/events/{uuid.uuid4()}/playback-url")

    assert resp.status_code == 404


# --- 已讀 ---------------------------------------------------------------


async def test_marking_an_event_read(client, uow):
    uow.given(a_timeline_event(is_read=False))

    resp = await client.patch(f"/events/{EVENT}", json={"is_read": True})

    assert resp.status_code == 200
    assert resp.json() == {"id": str(EVENT), "is_read": True}


async def test_patch_ignores_fields_the_client_may_not_set(client, uow):
    """規格審查 #10:body 只接受 is_read,不能讓用戶端改到 status。"""
    uow.given(a_timeline_event(status=EventStatus.READY, is_read=False))

    resp = await client.patch(
        f"/events/{EVENT}", json={"is_read": True, "status": "failed", "confidence_score": 0.1}
    )

    assert resp.status_code == 200
    stored = await uow.events.get(EVENT)
    assert stored.status is EventStatus.READY
    assert stored.confidence_score != 0.1


async def test_patch_without_is_read_is_rejected(client, uow):
    uow.given(a_timeline_event())

    resp = await client.patch(f"/events/{EVENT}", json={})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAL_001"


async def test_patching_someone_elses_event_is_404(client, uow, ownership):
    uow.given(a_timeline_event())
    ownership.owners = {DEVICE: BOB}

    resp = await client.patch(f"/events/{EVENT}", json={"is_read": True})

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "DEVICE_005"


# --- 健康檢查 -----------------------------------------------------------


async def test_health_does_not_touch_the_database(client):
    """LB 的健康檢查:資料層掛掉時這支仍要回 200,否則兩台節點會同時被判死。"""
    resp = await client.get("/health")

    assert resp.status_code == 200
