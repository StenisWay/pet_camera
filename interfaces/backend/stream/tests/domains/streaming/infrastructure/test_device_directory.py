"""Device 服務查詢 adapter(13_ADR 第 1 節:不跨服務直讀 devices 表)。

用 httpx 的 MockTransport,不需要真的跑起 Device 服務。
"""

import httpx
import pytest

from app.domains.streaming.domain.value_objects import DeviceStatus
from app.domains.streaming.infrastructure.device_directory import HttpDeviceDirectory
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.streaming.builders import ALICE, DEVICE_A, NOW

API_KEY = "internal-key"


def directory(handler) -> HttpDeviceDirectory:  # type: ignore[no-untyped-def]
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://device.internal"
    )
    return HttpDeviceDirectory(client, internal_api_key=API_KEY)


def responds(payload: dict, status_code: int = 200):  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        handler.request = request  # type: ignore[attr-defined]
        return httpx.Response(status_code, json=payload)

    return handler


async def test_maps_the_summary_to_a_snapshot() -> None:
    handler = responds(
        {
            "id": str(DEVICE_A),
            "name": "客廳",
            "user_id": str(ALICE),
            "status": "paired",
            "last_seen_at": NOW.isoformat(),
        }
    )

    snapshot = await directory(handler).find(DEVICE_A)

    assert snapshot is not None
    assert snapshot.device_id == DEVICE_A
    assert snapshot.owner_id == ALICE
    assert snapshot.status is DeviceStatus.PAIRED
    assert snapshot.last_seen_at == NOW


async def test_sends_the_internal_api_key() -> None:
    """內部端點只走 VCN 私有網路,共享金鑰是第二道防線。"""
    handler = responds({"id": str(DEVICE_A), "status": "paired", "user_id": str(ALICE)})

    await directory(handler).find(DEVICE_A)

    assert handler.request.headers["X-Internal-Api-Key"] == API_KEY  # type: ignore[attr-defined]
    assert handler.request.url.path == f"/internal/devices/{DEVICE_A}"  # type: ignore[attr-defined]


async def test_unpaired_device_has_no_owner() -> None:
    """user_id 為 None 代表未配對或已解除配對(device/__init__.py 的 DeviceSummary)。"""
    handler = responds({"id": str(DEVICE_A), "status": "pending", "user_id": None})

    snapshot = await directory(handler).find(DEVICE_A)

    assert snapshot is not None
    assert snapshot.owner_id is None


async def test_missing_last_seen_at_is_treated_as_never_reported() -> None:
    """**跨服務契約缺口**:DeviceSummary 目前不含 last_seen_at,
    但規格審查 #7 要求 Stream 自己檢查心跳新鮮度。欄位補上之前一律判為離線
    (fail-closed,13_ADR 第 4 節:Stream 選一致性)。見 README 的「待辦」。
    """
    handler = responds({"id": str(DEVICE_A), "status": "paired", "user_id": str(ALICE)})

    snapshot = await directory(handler).find(DEVICE_A)

    assert snapshot is not None
    assert snapshot.last_seen_at is None
    assert snapshot.is_online(NOW) is False


async def test_unknown_device_is_none_not_an_error() -> None:
    """查不到裝置不是錯誤——要不要當成 DEVICE_005 由 use case 決定。"""
    assert await directory(responds({}, status_code=404)).find(DEVICE_A) is None


@pytest.mark.parametrize("status_code", [400, 401, 500, 503])
async def test_other_failures_fail_closed(status_code: int) -> None:
    """寧可讓建立 session 失敗,也不假設鏡頭在線上。"""
    with pytest.raises(ServiceUnavailable):
        await directory(responds({}, status_code=status_code)).find(DEVICE_A)


async def test_transport_failure_fails_closed() -> None:
    def explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("device service unreachable")

    with pytest.raises(ServiceUnavailable):
        await directory(explode).find(DEVICE_A)
