"""PushNotifier 接到 Push 服務的內部端點(09_spec 第 3 節)。"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

import httpx

from app.domains.detection.application.ports import PushNotifier

TIMEOUT = httpx.Timeout(3.0)


class HttpPushNotifier(PushNotifier):
    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def notify_event_ready(
        self,
        *,
        device_id: UUID,
        event_id: UUID,
        confidence_score: Decimal,
        thumbnail_object_key: str | None,
        started_at: datetime,
    ) -> None:
        """POST /internal/notifications/event-ready,body 為 EventReadyNotification。

        Push 回 202 就結束,發送本身在它那邊背景進行——worker 不等發送結果
        (push/__init__.py 的說明)。這裡也不重試:推播晚到或漏掉一次,
        都比讓 worker 卡在通知上更好。
        """
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/internal/notifications/event-ready",
                headers={"X-Internal-Api-Key": self.api_key},
                json={
                    "event_id": str(event_id),
                    "device_id": str(device_id),
                    "confidence_score": float(confidence_score),
                    "thumbnail_object_key": thumbnail_object_key,
                    "started_at": started_at.isoformat(),
                },
            )
            resp.raise_for_status()
