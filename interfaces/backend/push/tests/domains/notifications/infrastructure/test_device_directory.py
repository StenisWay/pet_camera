"""Device 服務 GET /internal/devices/{device_id} 的 client(04_spec 第 3 節)。"""

import httpx
import pytest

from app.core.config import Settings
from app.domains.notifications.application.ports import DeviceInfo
from app.domains.notifications.infrastructure.device_directory import HttpDeviceDirectory
from tests.domains.notifications.builders import DEVICE_ID, OWNER

SETTINGS = Settings(device_service_base_url="http://device.test", internal_api_key="k-1")


def _directory(handler) -> HttpDeviceDirectory:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpDeviceDirectory(SETTINGS, client=client)


async def test_reads_name_and_owner_with_the_internal_key():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-Internal-Api-Key")
        return httpx.Response(
            200,
            json={"id": str(DEVICE_ID), "name": "客廳", "user_id": str(OWNER), "status": "online"},
        )

    device = await _directory(handler).find(DEVICE_ID)

    assert device == DeviceInfo(id=DEVICE_ID, name="客廳", owner_id=OWNER)
    assert seen == {"url": f"http://device.test/internal/devices/{DEVICE_ID}", "key": "k-1"}


async def test_null_user_id_means_no_owner():
    """04_spec:user_id 為 null 代表未配對或已解除配對,Push 捨棄通知。"""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"id": str(DEVICE_ID), "name": "客廳", "user_id": None, "status": "pending"}
        )

    assert (await _directory(handler).find(DEVICE_ID)).owner_id is None


async def test_unknown_device_returns_none():
    assert await _directory(lambda _: httpx.Response(404)).find(DEVICE_ID) is None


@pytest.mark.parametrize("status", [401, 403, 500, 503])
async def test_other_failures_raise_so_the_caller_can_retry(status):
    with pytest.raises(httpx.HTTPStatusError):
        await _directory(lambda _: httpx.Response(status)).find(DEVICE_ID)
