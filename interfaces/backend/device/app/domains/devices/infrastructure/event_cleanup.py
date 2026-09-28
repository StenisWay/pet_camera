"""EventCleanup 的實作:呼叫 Event 服務的內部端點(規格審查 #7)。

這個端點目前**尚未實作**——Event 服務還沒做到這裡。規格書裡也找不到它:
全 rule_doc 只有 Album 的 DELETE /internal/users/{user_id}/media 這一個內部端點,
而 04_spec 第 2.3 節與 01_資料模型 第 6 節都要求移除裝置時一併清掉事件與 R2 物件。
審查結論是比照 Album 的前例新增,並寫回 07_spec / 08_spec 第 3 節。

本服務這一側已經完成:port、adapter、fail-closed 流程與測試都在。
Event 服務那一側實作完成前,DELETE /devices/{id} 在真實環境會得到 SRV_002,
這正是 fail-closed 期望的行為——裝置維持原狀,不會留下殘留的事件。
"""

import uuid

import httpx

from app.domains.devices.application.ports import EventCleanup
from app.domains.devices.domain.exceptions import EventCleanupFailed


class HttpEventCleanup(EventCleanup):
    def __init__(self, *, base_url: str, api_key: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    async def delete_device_events(self, device_id: uuid.UUID) -> None:
        url = f"{self.base_url}/internal/devices/{device_id}/events"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.delete(
                    url, headers={"X-Internal-Api-Key": self.api_key}
                )
        except httpx.HTTPError as exc:
            raise EventCleanupFailed() from exc

        # 404 視為成功:該裝置本來就沒有事件。端點必須是冪等的(見 port 的合約),
        # 因為 fail-closed 流程會讓使用者重試。
        if response.status_code not in (200, 204, 404):
            raise EventCleanupFailed()
