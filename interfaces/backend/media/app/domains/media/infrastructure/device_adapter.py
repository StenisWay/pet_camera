"""DeviceDirectory 接到 Device 服務。

比照 stream/__init__.py:需要裝置擁有者與線上狀態時呼叫 Device 服務,不直接讀
它的資料表。
"""

import uuid

import httpx

from app.core.config import Settings
from app.domains.media.application.ports import DeviceDirectory, SourceDevice
from app.shared_kernel.errors import ServiceUnavailable


class HttpDeviceDirectory(DeviceDirectory):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.device_service_url,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
            timeout=5.0,
        )

    async def get(self, device_id: uuid.UUID) -> SourceDevice | None:
        try:
            response = await self._client.get(f"/internal/devices/{device_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # 對方服務故障不是使用者的錯,回 SRV_002(503)讓前端提供重試,
            # 而不是讓原始例外變成沒有錯誤碼的 500
            raise ServiceUnavailable() from exc
        payload = response.json()
        owner_id = payload.get("user_id")
        if owner_id is None:
            # 未配對的裝置沒有擁有者(資料模型 §2.2:status = pending 時 user_id 為 null),
            # 對任何使用者而言都等同於不存在
            return None
        return SourceDevice(
            id=uuid.UUID(payload["id"]),
            owner_id=uuid.UUID(owner_id),
            # 06_spec STREAM_001 用的是同一個判斷:offline 代表已配對但失聯
            is_online=payload["status"] == "paired",
        )

    async def aclose(self) -> None:
        await self._client.aclose()
