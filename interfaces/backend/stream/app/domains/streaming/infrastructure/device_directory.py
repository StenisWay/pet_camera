"""向 Device 服務查詢鏡頭狀態(13_ADR 第 1 節:不跨服務直讀 devices 表)。

呼叫 GET /internal/devices/{device_id},只走 VCN 私有網路,X-Internal-Api-Key 把關。

**待辦(跨服務契約缺口)**:Device 服務的 DeviceSummary 目前不含 last_seen_at,
但 06_spec 規格審查 #7 決議由 Stream 自己檢查心跳新鮮度才能讓 STREAM_001 真的觸發。
欄位補上之前,沒有 last_seen_at 的回應一律判為離線(fail-closed,13_ADR 第 4 節:
Stream 選一致性)。詳見 README 的「待辦」。
"""

import logging
import uuid
from datetime import datetime

import httpx

from app.domains.streaming.application.ports import DeviceDirectory
from app.domains.streaming.domain.value_objects import DeviceSnapshot, DeviceStatus
from app.shared_kernel.errors import ServiceUnavailable

logger = logging.getLogger(__name__)


class HttpDeviceDirectory(DeviceDirectory):
    def __init__(self, client: httpx.AsyncClient, *, internal_api_key: str) -> None:
        self._client = client
        self._internal_api_key = internal_api_key

    async def find(self, device_id: uuid.UUID) -> DeviceSnapshot | None:
        try:
            response = await self._client.get(
                f"/internal/devices/{device_id}",
                headers={"X-Internal-Api-Key": self._internal_api_key},
            )
        except httpx.HTTPError as exc:
            # 查不到裝置狀態時寧可讓建立 session 失敗,也不假設鏡頭在線上
            raise ServiceUnavailable() from exc

        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("device service returned %s for %s", response.status_code, device_id)
            raise ServiceUnavailable()

        return _to_snapshot(response.json())


def _to_snapshot(payload: dict[str, object]) -> DeviceSnapshot:
    owner = payload.get("user_id")
    return DeviceSnapshot(
        device_id=uuid.UUID(str(payload["id"])),
        owner_id=uuid.UUID(str(owner)) if owner else None,
        status=DeviceStatus(str(payload["status"])),
        last_seen_at=_parse_time(payload.get("last_seen_at")),
    )


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))
