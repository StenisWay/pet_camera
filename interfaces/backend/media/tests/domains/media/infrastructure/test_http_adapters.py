"""跨服務 HTTP adapter:對方回應 → 本領域語言的轉換。

用 httpx.MockTransport 模擬對方服務,不需要真的連線,所以不標 integration。
這裡驗的是 adapter 自己的規則(404 → 不存在、未配對 → 不存在、連不上 → 503),
不是對方服務的行為。
"""

import base64
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.core.config import Settings
from app.domains.media.domain.exceptions import ScreenshotSourceUnavailable
from app.domains.media.infrastructure.device_adapter import HttpDeviceDirectory
from app.domains.media.infrastructure.event_adapter import HttpEventSource
from app.domains.media.infrastructure.worker_adapter import HttpWorker
from app.shared_kernel.errors import ServiceUnavailable

SETTINGS = Settings(internal_api_key="k-internal")
OWNER = uuid.uuid4()
DEVICE = uuid.uuid4()
EVENT = uuid.uuid4()

Handler = Callable[[httpx.Request], httpx.Response]


def client_for(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://upstream",
        headers={"X-Internal-Api-Key": SETTINGS.internal_api_key},
        transport=httpx.MockTransport(handler),
    )


def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def server_error(_: httpx.Request) -> httpx.Response:
    return httpx.Response(502)


# ---------- Device 服務 ----------


def device_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(DEVICE),
        "name": "客廳",
        "user_id": str(OWNER),
        "status": "paired",
    }
    payload.update(overrides)
    return payload


async def test_device_directory_maps_a_paired_device():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=device_payload())

    device = await HttpDeviceDirectory(SETTINGS, client_for(handler)).get(DEVICE)

    assert device is not None
    assert device.owner_id == OWNER
    assert device.is_online is True
    assert seen[0].url.path == f"/internal/devices/{DEVICE}"
    assert seen[0].headers["X-Internal-Api-Key"] == "k-internal"


async def test_device_directory_treats_offline_device_as_not_online():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=device_payload(status="offline"))

    device = await HttpDeviceDirectory(SETTINGS, client_for(handler)).get(DEVICE)

    assert device is not None
    assert device.is_online is False


async def test_device_directory_returns_none_when_device_is_missing():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    assert await HttpDeviceDirectory(SETTINGS, client_for(handler)).get(DEVICE) is None


async def test_device_directory_treats_unpaired_device_as_missing():
    """pending 的裝置沒有擁有者,對任何使用者都等同於不存在(資料模型 §2.2)。"""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=device_payload(user_id=None, status="pending"))

    assert await HttpDeviceDirectory(SETTINGS, client_for(handler)).get(DEVICE) is None


@pytest.mark.parametrize("handler", [unreachable, server_error], ids=["unreachable", "5xx"])
async def test_device_directory_raises_service_unavailable_when_device_service_is_down(handler):
    """假設:Device 服務故障回 SRV_002(503),而不是沒有錯誤碼的 500。"""
    with pytest.raises(ServiceUnavailable):
        await HttpDeviceDirectory(SETTINGS, client_for(handler)).get(DEVICE)


# ---------- Event 服務 ----------


def event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(EVENT),
        "owner_id": str(OWNER),
        "device_id": str(DEVICE),
        "status": "ready",
        "started_at": "2026-09-20T10:00:00Z",
        "duration_sec": 45,
    }
    payload.update(overrides)
    return payload


async def test_event_source_maps_the_event_with_its_owner():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=event_payload())

    event = await HttpEventSource(SETTINGS, client_for(handler)).get(EVENT)

    assert event is not None
    assert event.owner_id == OWNER
    assert event.device_id == DEVICE
    assert event.status == "ready"
    assert event.duration_sec == 45
    assert event.started_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
    assert seen[0].url.path == f"/internal/events/{EVENT}"


async def test_event_source_returns_none_when_event_is_missing():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    assert await HttpEventSource(SETTINGS, client_for(handler)).get(EVENT) is None


@pytest.mark.parametrize("handler", [unreachable, server_error], ids=["unreachable", "5xx"])
async def test_event_source_raises_service_unavailable_when_event_service_is_down(handler):
    with pytest.raises(ServiceUnavailable):
        await HttpEventSource(SETTINGS, client_for(handler)).get(EVENT)


# ---------- VM-3 worker ----------


def frame_response(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "image": base64.b64encode(b"jpeg").decode(),
            "thumbnail": base64.b64encode(b"thumb").decode(),
        },
    )


async def test_worker_captures_a_live_frame_with_its_thumbnail():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return frame_response(request)

    frame = await HttpWorker(SETTINGS, client_for(handler)).capture_live_frame(DEVICE)

    assert frame.image == b"jpeg"
    assert frame.thumbnail == b"thumb"
    assert seen[0].url.path == "/internal/frames"
    assert seen[0].read() == f'{{"device_id":"{DEVICE}"}}'.encode()


async def test_worker_captures_an_event_frame_at_the_given_offset():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return frame_response(request)

    await HttpWorker(SETTINGS, client_for(handler)).capture_event_frame(EVENT, offset_sec=12)

    assert seen[0].read() == f'{{"event_id":"{EVENT}","offset_sec":12}}'.encode()


@pytest.mark.parametrize("handler", [unreachable, server_error], ids=["unreachable", "5xx"])
async def test_worker_frame_failure_is_screenshot_source_unavailable(handler):
    with pytest.raises(ScreenshotSourceUnavailable):
        await HttpWorker(SETTINGS, client_for(handler)).capture_live_frame(DEVICE)


async def test_worker_dispatches_a_clip_with_target_keys():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    item_id = uuid.uuid4()
    await HttpWorker(SETTINGS, client_for(handler)).dispatch(
        media_item_id=item_id,
        source_event_id=EVENT,
        start_sec=5,
        end_sec=20,
        object_key="media/k.mp4",
        thumbnail_object_key="media-thumbnails/k.jpg",
    )

    assert seen[0].url.path == "/internal/clips"
    assert json.loads(seen[0].read()) == {
        "media_item_id": str(item_id),
        "source_event_id": str(EVENT),
        "start_sec": 5,
        "end_sec": 20,
        "object_key": "media/k.mp4",
        "thumbnail_object_key": "media-thumbnails/k.jpg",
    }


@pytest.mark.parametrize("handler", [unreachable, server_error], ids=["unreachable", "5xx"])
async def test_worker_dispatch_failure_propagates_so_the_item_is_marked_failed(handler):
    """ClipWorker 的承諾:派不出去就拋例外,由 use case 標 failed 並回 CLIP_002。"""
    with pytest.raises(Exception):  # noqa: B017 — 承諾只要求「拋例外」,不限型別
        await HttpWorker(SETTINGS, client_for(handler)).dispatch(
            media_item_id=uuid.uuid4(),
            source_event_id=EVENT,
            start_sec=0,
            end_sec=10,
            object_key="media/k.mp4",
            thumbnail_object_key="media-thumbnails/k.jpg",
        )
