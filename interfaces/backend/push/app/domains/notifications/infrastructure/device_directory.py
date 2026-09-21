"""DeviceDirectory → Device 服務 GET /internal/devices/{device_id}(04_spec 第 3 節)。

走 VCN 私有網路,夾帶 X-Internal-Api-Key。404 表示裝置不存在;其餘失敗往外丟,
由 use case 延後重試(13_ADR 第 4 節,發送路徑選可用性)。
"""

import uuid

import httpx

from app.core.config import Settings
from app.domains.notifications.application.ports import DeviceDirectory, DeviceInfo


class HttpDeviceDirectory(DeviceDirectory):
    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._base_url = settings.device_service_base_url.rstrip("/")
        self._headers = {"X-Internal-Api-Key": settings.internal_api_key}
        self._client = client or httpx.AsyncClient(timeout=settings.device_service_timeout_seconds)

    async def find(self, device_id: uuid.UUID) -> DeviceInfo | None:
        response = await self._client.get(
            f"{self._base_url}/internal/devices/{device_id}", headers=self._headers
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = response.json()
        owner = body.get("user_id")
        return DeviceInfo(
            id=uuid.UUID(body["id"]),
            name=body["name"],
            owner_id=uuid.UUID(owner) if owner else None,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
