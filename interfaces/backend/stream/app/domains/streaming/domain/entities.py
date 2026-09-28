"""直播 session 聚合。業務規則寫在方法裡,時間由外部傳入。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum

from app.domains.streaming.domain.exceptions import SessionExpired
from app.domains.streaming.domain.value_objects import IceCandidate, TurnCredentials


class SignalingState(StrEnum):
    CREATED = "created"
    OFFERED = "offered"
    ANSWERED = "answered"


class Peer(StrEnum):
    VIEWER = "viewer"
    CAMERA = "camera"


@dataclass
class StreamSession:
    id: uuid.UUID
    device_id: uuid.UUID
    owner_id: uuid.UUID
    turn_credentials: TurnCredentials
    created_at: datetime
    expires_at: datetime
    state: SignalingState = SignalingState.CREATED
    offer_sdp: str | None = None
    answer_sdp: str | None = None
    viewer_candidates: list[IceCandidate] = field(default_factory=list)
    camera_candidates: list[IceCandidate] = field(default_factory=list)

    @classmethod
    def open(
        cls,
        *,
        id: uuid.UUID,
        device_id: uuid.UUID,
        owner_id: uuid.UUID,
        turn_credentials: TurnCredentials,
        now: datetime,
        ttl: timedelta,
    ) -> StreamSession:
        return cls(
            id=id,
            device_id=device_id,
            owner_id=owner_id,
            turn_credentials=turn_credentials,
            created_at=now,
            expires_at=now + ttl,
        )

    def is_expired(self, now: datetime) -> bool:
        """到期當下即視為失效(>=),不留模糊地帶。"""
        return now >= self.expires_at

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        return self.owner_id == user_id

    def submit_offer(self, sdp: str, now: datetime) -> None:
        """送出或重送 offer。重送視為重新協商:舊的 answer 立刻作廢。

        第 2.3 節的 ICE 重連會重送 offer,若留著上一輪的 answer,觀看端會拿到
        對不上這次 offer 的舊 answer。
        """
        self._guard_live(now)
        self.offer_sdp = sdp
        self.answer_sdp = None
        self.state = SignalingState.OFFERED

    def accept_answer(self, sdp: str, now: datetime) -> None:
        self._guard_live(now)
        self.answer_sdp = sdp
        self.state = SignalingState.ANSWERED

    def add_candidate(self, peer: Peer, candidate: IceCandidate, now: datetime) -> None:
        self._guard_live(now)
        self._candidates_of(peer).append(candidate)

    def candidates_for(self, peer: Peer, since: int) -> list[IceCandidate]:
        """回傳 peer 這一側送出的 candidate,從索引 since 之後開始(增量輪詢)。"""
        return self._candidates_of(peer)[since:]

    def _candidates_of(self, peer: Peer) -> list[IceCandidate]:
        return self.viewer_candidates if peer is Peer.VIEWER else self.camera_candidates

    def _guard_live(self, now: datetime) -> None:
        if self.is_expired(now):
            raise SessionExpired()
