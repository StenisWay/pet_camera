"""DeviceOwnership 接到 Device 服務的內部端點。

跨服務呼叫只走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節),
以 X-Internal-Api-Key 把關(04_spec 第 3 節)。
"""

from uuid import UUID

import httpx

from app.domains.timeline.application.ports import DeviceOwnership
from app.shared_kernel.errors import ServiceUnavailable

TIMEOUT = httpx.Timeout(3.0)


class HttpDeviceOwnership(DeviceOwnership):
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def is_owned_by(self, device_id: UUID, user_id: UUID) -> bool:
        """GET /internal/devices/{device_id} → DeviceSummary。

        404(裝置不存在)與 user_id 為 null(未配對)都回 False,由呼叫端統一轉成
        404 DEVICE_005——對使用者而言這三種情況沒有區別,分開回應只會洩漏存在性。

        Device 服務連不上時丟 ServiceUnavailable(503),不是「無權限」:
        驗證不了擁有者就不能放行,但也不該告訴使用者「這不是你的裝置」。
        """
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/internal/devices/{device_id}",
                    headers={"X-Internal-Api-Key": self.api_key},
                )
        except httpx.HTTPError as exc:
            raise ServiceUnavailable() from exc

        if resp.status_code == 404:
            return False
        if resp.status_code >= 500:
            raise ServiceUnavailable()
        if resp.status_code != 200:
            raise ServiceUnavailable()

        owner = resp.json().get("user_id")
        return owner is not None and UUID(str(owner)) == user_id
