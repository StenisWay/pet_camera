"""ICE candidate 的雙向交換(第 3.1、3.2 節)。

兩側用同一組 use case:差別只在「我是哪一側」,由 router 決定,不由 use case 猜。
"""

import uuid

from app.domains.streaming.application.dtos import CandidateBatch
from app.domains.streaming.application.use_cases.session_access import load_session
from app.domains.streaming.domain.entities import Peer
from app.domains.streaming.domain.repositories import StreamSessionRepository
from app.domains.streaming.domain.value_objects import IceCandidate
from app.shared_kernel.ports import Clock


class AddIceCandidates:
    def __init__(self, sessions: StreamSessionRepository, clock: Clock) -> None:
        self.sessions = sessions
        self.clock = clock

    async def execute(
        self,
        *,
        device_id: uuid.UUID,
        session_id: uuid.UUID,
        peer: Peer,
        candidates: list[IceCandidate],
        requester_id: uuid.UUID | None = None,
    ) -> None:
        now = self.clock.now()
        session = await load_session(
            self.sessions, session_id, device_id=device_id, requester_id=requester_id
        )
        for candidate in candidates:
            session.add_candidate(peer, candidate, now)
        await self.sessions.save(session)


class FetchIceCandidates:
    def __init__(self, sessions: StreamSessionRepository) -> None:
        self.sessions = sessions

    async def execute(
        self,
        *,
        device_id: uuid.UUID,
        session_id: uuid.UUID,
        peer: Peer,
        since: int,
        requester_id: uuid.UUID | None = None,
    ) -> CandidateBatch:
        """peer 是「要讀誰送的」:觀看端讀鏡頭端的,鏡頭端讀觀看端的。"""
        session = await load_session(
            self.sessions, session_id, device_id=device_id, requester_id=requester_id
        )
        candidates = session.candidates_for(peer, since=since)
        return CandidateBatch(candidates=candidates, next_since=since + len(candidates))
