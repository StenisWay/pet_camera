"""EventSource 接到 Event 服務(規格審查 #7)。

events 表屬 Event 服務,不可直接讀——比照 stream/__init__.py 立下的先例,跨服務
一律走對方的 API。用的是內部端點 `GET /internal/events/{id}`:它比時間軸的對外
端點多回一個 owner_id,因為 events 表本身沒有 user_id,Media 無法自行判斷擁有者。

只走 VCN 私有網路、不經 Load Balancer(13_ADR 第 1 節),共享金鑰是第二道防線。
"""

import uuid
from datetime import datetime

import httpx

from app.core.config import Settings
from app.domains.media.application.ports import EventSource
from app.domains.media.domain.entities import SourceEvent
from app.shared_kernel.errors import ServiceUnavailable


class HttpEventSource(EventSource):
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.event_service_url,
            headers={"X-Internal-Api-Key": settings.internal_api_key},
            timeout=5.0,
        )

    async def get(self, event_id: uuid.UUID) -> SourceEvent | None:
        try:
            response = await self._client.get(f"/internal/events/{event_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()
        except httpx.HTTPError as exc:
            # 對方服務故障不是使用者的錯,回 SRV_002(503)讓前端提供重試,
            # 而不是讓原始例外變成沒有錯誤碼的 500
            raise ServiceUnavailable() from exc
        payload = response.json()
        return SourceEvent(
            id=uuid.UUID(payload["id"]),
            owner_id=uuid.UUID(payload["owner_id"]),
            device_id=uuid.UUID(payload["device_id"]),
            status=payload["status"],
            started_at=datetime.fromisoformat(payload["started_at"]),
            duration_sec=payload["duration_sec"],
        )

    async def aclose(self) -> None:
        await self._client.aclose()
