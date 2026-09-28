"""HTTP 契約(11_spec 第 3、5 節)。

這一層只驗證「業務規則有沒有正確接上 HTTP」——狀態碼、錯誤碼、回應欄位、權限。
規則本身已在 domain 與 application 窮盡,不在這裡重測。
"""

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import get_current_user_id
from app.domains.media.application.ports import SourceDevice
from app.domains.media.domain.entities import MediaItemStatus
from app.domains.media.presentation.dependencies import (
    get_clip_worker,
    get_clock,
    get_device_directory,
    get_event_source,
    get_frame_source,
    get_id_generator,
    get_media_storage,
    get_media_uow,
    get_rate_limit_counter,
)
from app.main import create_app
from tests.domains.media.builders import (
    DEVICE,
    EVENT,
    ITEM,
    NOW,
    OTHER_USER,
    OWNER,
    an_event,
    an_item,
)
from tests.domains.media.fakes import (
    FakeClipWorker,
    FakeDeviceDirectory,
    FakeEventSource,
    FakeFrameSource,
    FakeMediaStorage,
    FakeMediaUnitOfWork,
    FakeRateLimitCounter,
    FixedClock,
    SequentialIds,
)

INTERNAL_KEY = "change-me-internal"


@pytest.fixture
def uow():
    return FakeMediaUnitOfWork()


@pytest.fixture
def worker():
    return FakeClipWorker()


@pytest.fixture
def frames():
    return FakeFrameSource()


@pytest.fixture
def counter():
    return FakeRateLimitCounter()


@pytest.fixture
def ids():
    return SequentialIds()


@pytest.fixture
def app(uow, worker, frames, counter, ids):
    app = create_app(lifespan_enabled=False)
    app.dependency_overrides.update(
        {
            get_media_uow: lambda: uow,
            get_device_directory: lambda: FakeDeviceDirectory(
                {DEVICE: SourceDevice(id=DEVICE, owner_id=OWNER, is_online=True)}
            ),
            get_event_source: lambda: FakeEventSource({EVENT: an_event(duration_sec=45)}),
            get_frame_source: lambda: frames,
            get_clip_worker: lambda: worker,
            get_media_storage: lambda: FakeMediaStorage(),
            get_clock: lambda: FixedClock(NOW),
            get_id_generator: lambda: ids,
            get_rate_limit_counter: lambda: counter,
            get_current_user_id: lambda: OWNER,
        }
    )
    return app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --- 截圖 -------------------------------------------------------------------


async def test_live_screenshot_returns_a_ready_item(client):
    """審查 #1:截圖同步完成,201 回傳的就是 ready 的項目。"""
    resp = await client.post(f"/devices/{DEVICE}/screenshot")

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert body["type"] == "photo"


async def test_response_never_exposes_the_storage_layout(client):
    """R2 object key 是內部細節,對外只給 presigned URL(12_spec 第 3 節)。"""
    resp = await client.post(f"/devices/{DEVICE}/screenshot")

    body = resp.json()
    assert "object_key" not in body
    assert "thumbnail_object_key" not in body
    assert body["content_url"].startswith("https://")


async def test_event_screenshot_takes_an_offset(client, frames):
    """審查 #5:時間點以事件開始為基準的整數秒。"""
    resp = await client.post(f"/events/{EVENT}/screenshot", json={"offset_sec": 12})

    assert resp.status_code == 201
    assert frames.calls == [("event", EVENT, 12)]


async def test_screenshot_of_offline_camera_reports_screenshot_001(client, app):
    app.dependency_overrides[get_device_directory] = lambda: FakeDeviceDirectory(
        {DEVICE: SourceDevice(id=DEVICE, owner_id=OWNER, is_online=False)}
    )

    resp = await client.post(f"/devices/{DEVICE}/screenshot")

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SCREENSHOT_001"


# --- 剪輯 -------------------------------------------------------------------


async def test_clip_request_is_accepted_for_background_processing(client):
    """11_spec 第 4 節:送出後顯示「處理中」並停留於當前頁面。"""
    resp = await client.post(f"/events/{EVENT}/clip", json={"start_sec": 5, "end_sec": 20})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert body["duration_sec"] == 15
    assert body["content_url"] is None


async def test_clip_longer_than_the_limit_reports_clip_003(client):
    """11_spec 第 5 節:CLIP_003,400,Inline 於剪輯時間選取元件。"""
    resp = await client.post(f"/events/{EVENT}/clip", json={"start_sec": 0, "end_sec": 61})

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CLIP_003"


async def test_clip_of_expired_source_reports_clip_001(client, app):
    """11_spec 第 5 節:CLIP_001,410。"""
    expired = an_event(started_at=NOW - timedelta(days=8))
    app.dependency_overrides[get_event_source] = lambda: FakeEventSource({EVENT: expired})

    resp = await client.post(f"/events/{EVENT}/clip", json={"start_sec": 0, "end_sec": 10})

    assert resp.status_code == 410
    assert resp.json()["error"]["code"] == "CLIP_001"


@pytest.mark.parametrize(
    "payload",
    [
        {"start_sec": 20, "end_sec": 10},  # 起訖顛倒
        {"start_sec": -1, "end_sec": 10},  # 負數
        {"start_sec": 40, "end_sec": 50},  # 超出來源長度(45 秒)
        {"start_sec": 0},  # 缺欄位
        {"start_sec": "a", "end_sec": 10},  # 型別錯誤
    ],
)
async def test_invalid_clip_range_reports_val_001(client, payload):
    """審查 #14:範圍類錯誤一律 VAL_001,不佔用 CLIP_003。"""
    resp = await client.post(f"/events/{EVENT}/clip", json=payload)

    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VAL_001"


# --- 權限 -------------------------------------------------------------------


async def test_clip_of_another_users_event_is_404_not_403(client, app):
    """審查 #6:不洩漏資源存在性,所以不回 403。"""
    app.dependency_overrides[get_event_source] = lambda: FakeEventSource(
        {EVENT: an_event(owner_id=OTHER_USER)}
    )

    resp = await client.post(f"/events/{EVENT}/clip", json={"start_sec": 0, "end_sec": 10})

    assert resp.status_code == 404


async def test_anonymous_request_is_rejected(app):
    """10_錯誤處理與狀態規範.md 第 3 節:AUTH_001,401,阻斷式導向登入頁。"""
    app.dependency_overrides.pop(get_current_user_id)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post(f"/devices/{DEVICE}/screenshot")

    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTH_001"


# --- 查詢 -------------------------------------------------------------------


async def test_ready_item_is_returned_with_a_link(client, uow):
    uow.given(an_item(status=MediaItemStatus.READY, object_key="media/a/x.jpg"))

    resp = await client.get(f"/media/{ITEM}")

    assert resp.status_code == 200
    assert resp.json()["content_url"].startswith("https://")


async def test_processing_item_is_returned_without_a_link(client, uow):
    """11_spec 第 4 節:processing 顯示 spinner,完成前不可點擊播放。"""
    uow.given(an_item(status=MediaItemStatus.PROCESSING))

    resp = await client.get(f"/media/{ITEM}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "processing"
    assert body["content_url"] is None


async def test_other_users_item_is_404(client, uow):
    uow.given(an_item(owner_id=OTHER_USER, status=MediaItemStatus.READY))

    resp = await client.get(f"/media/{ITEM}")

    assert resp.status_code == 404


# --- 內部端點 ---------------------------------------------------------------


async def test_worker_callback_publishes_the_item(client, uow):
    """審查 #3:worker 轉檔完成後回呼。"""
    uow.given(an_item(status=MediaItemStatus.PROCESSING))

    resp = await client.post(
        f"/internal/media/{ITEM}/ready",
        json={"object_key": "media/a/x.mp4", "thumbnail_object_key": "media-thumbnails/a/x.jpg"},
        headers={"X-Internal-Api-Key": INTERNAL_KEY},
    )

    assert resp.status_code == 204
    assert uow.media.committed[ITEM].status is MediaItemStatus.READY


async def test_worker_callback_without_the_shared_key_is_rejected(client, uow):
    """內部端點只走 VCN 私網,共享金鑰是第二道防線(13_ADR 第 1 節)。"""
    uow.given(an_item(status=MediaItemStatus.PROCESSING))

    resp = await client.post(
        f"/internal/media/{ITEM}/failed", json={}, headers={"X-Internal-Api-Key": "wrong"}
    )

    assert resp.status_code == 403
    assert uow.media.committed[ITEM].status is MediaItemStatus.PROCESSING


async def test_internal_endpoints_are_not_reachable_with_a_user_token(client, uow):
    """使用者的 access token 不能拿來推進處理狀態。"""
    uow.given(an_item(status=MediaItemStatus.PROCESSING))

    resp = await client.post(f"/internal/media/{ITEM}/failed", json={})

    assert resp.status_code == 403


# --- 限流 -------------------------------------------------------------------


async def test_screenshot_is_rate_limited(client):
    """審查 #15:擷幀吃的是 VM-3 的 2 OCPU,全系統瓶頸。預設 10 次/分鐘。"""
    for _ in range(10):
        assert (await client.post(f"/devices/{DEVICE}/screenshot")).status_code == 201

    resp = await client.post(f"/devices/{DEVICE}/screenshot")

    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_001"


async def test_clip_has_a_tighter_budget_than_screenshot(client):
    """轉碼比擷幀貴得多,預設 3 次/分鐘。"""
    for start in (0, 1, 2):
        resp = await client.post(
            f"/events/{EVENT}/clip", json={"start_sec": start, "end_sec": start + 10}
        )
        assert resp.status_code == 202

    resp = await client.post(f"/events/{EVENT}/clip", json={"start_sec": 5, "end_sec": 20})

    assert resp.status_code == 429


async def test_health_check_does_not_touch_the_database(client):
    """13_ADR 第 3 節:VM-3 掛掉不該讓兩台服務節點被 LB 判定為不健康。"""
    resp = await client.get("/health")

    assert resp.status_code == 200
