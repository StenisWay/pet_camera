"""觀看端送出 SDP offer 並同步等待鏡頭端的 answer(第 3.1 節)。"""

import uuid
from datetime import timedelta

from app.domains.streaming.application.ports import SignalingEvents
from app.domains.streaming.application.use_cases.session_access import load_session
from app.domains.streaming.domain.exceptions import SessionExpired, SignalingTimeout
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.shared_kernel.ports import Clock


class SubmitOffer:
    def __init__(
        self,
        sessions: StreamSessionRepository,
        events: SignalingEvents,
        clock: Clock,
        *,
        answer_timeout: timedelta,
    ) -> None:
        self.sessions = sessions
        self.events = events
        self.clock = clock
        self.answer_timeout = answer_timeout

    async def execute(
        self,
        *,
        device_id: uuid.UUID,
        session_id: uuid.UUID,
        requester_id: uuid.UUID,
        sdp: str,
    ) -> str:
        now = self.clock.now()
        session = await load_session(
            self.sessions, session_id, device_id=device_id, requester_id=requester_id
        )
        session.submit_offer(sdp, now)
        await self.sessions.save(session)
        # 先存再通知:通知先發出去的話,另一個複本可能讀到還沒寫入的舊狀態
        await self.events.announce_offer(device_id)

        await self.events.wait_for_answer(session_id, self.answer_timeout)

        # 不論是被通知喚醒還是等到逾時,都重讀一次:Pub/Sub 不補送,answer 若在我們
        # 訂閱之前就發布了,通知會遺失,但資料已經在 Redis 裡。通知只是「可以早點去看」
        # 的提示,不是真相。answer 本來也可能寫在另一台複本上,手上這份一定是舊的。
        answered = await self.sessions.get(session_id)
        if answered is None:
            # 等待期間被接管或 TTL 到期
            raise SessionExpired()
        if answered.answer_sdp is None:
            raise SignalingTimeout()
        return answered.answer_sdp
