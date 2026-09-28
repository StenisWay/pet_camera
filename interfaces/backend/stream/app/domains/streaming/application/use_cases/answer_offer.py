"""鏡頭端回覆 SDP answer(第 3.2 節,內部路由)。"""

import uuid

from app.domains.streaming.application.ports import SignalingEvents
from app.domains.streaming.application.use_cases.session_access import load_session
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.shared_kernel.ports import Clock


class AnswerOffer:
    def __init__(
        self,
        sessions: StreamSessionRepository,
        events: SignalingEvents,
        clock: Clock,
    ) -> None:
        self.sessions = sessions
        self.events = events
        self.clock = clock

    async def execute(self, *, device_id: uuid.UUID, session_id: uuid.UUID, sdp: str) -> None:
        # requester_id 留空:呼叫者是鏡頭,身分由裝置憑證驗證,不是 JWT 的使用者
        session = await load_session(self.sessions, session_id, device_id=device_id)
        session.accept_answer(sdp, self.clock.now())
        await self.sessions.save(session)
        await self.events.announce_answer(session_id)
