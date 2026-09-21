"""鏡頭端長輪詢待處理的 offer(第 3.2 節)。逾時 30 秒回 None -> 204。"""

import uuid
from datetime import timedelta

from app.domains.streaming.application.dtos import PendingOffer
from app.domains.streaming.application.ports import SignalingEvents
from app.domains.streaming.domain.entities import SignalingState, StreamSession
from app.domains.streaming.domain.repositories import StreamSessionRepository


class FetchPendingOffer:
    def __init__(
        self,
        sessions: StreamSessionRepository,
        events: SignalingEvents,
        *,
        poll_timeout: timedelta,
    ) -> None:
        self.sessions = sessions
        self.events = events
        self.poll_timeout = poll_timeout

    async def execute(self, device_id: uuid.UUID) -> PendingOffer | None:
        # 先查一次再等:offer 可能在鏡頭重新發起輪詢之前就送到了,
        # 只等通知會漏掉它,鏡頭要再空轉 30 秒才會看到
        pending = self._pending(await self.sessions.get_active_for_device(device_id))
        if pending is not None:
            return pending

        # 同樣不把通知當成真相:等待結束後一律重查一次(見 redis_signaling.py)
        await self.events.wait_for_offer(device_id, self.poll_timeout)
        return self._pending(await self.sessions.get_active_for_device(device_id))

    @staticmethod
    def _pending(session: StreamSession | None) -> PendingOffer | None:
        """只有「已送出 offer 但還沒被回覆」才算待處理。

        已經 answered 的不再回傳,否則鏡頭端每輪都會拿到同一個 offer 重新協商。
        """
        if session is None or session.offer_sdp is None:
            return None
        if session.state is not SignalingState.OFFERED:
            return None
        return PendingOffer(session_id=session.id, sdp=session.offer_sdp)
