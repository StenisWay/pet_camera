"""HTTP 契約(06_spec_即時串流.md 第 3 節)。Pydantic 只出現在這一層。

ICE candidate 的欄位沿用 WebRTC 的 sdpMid / sdpMLineIndex 命名:前端直接把
RTCIceCandidate 丟上來、把回傳的丟進 addIceCandidate,不必兩邊各做一次轉換。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domains.streaming.domain.entities import StreamSession
from app.domains.streaming.domain.value_objects import IceCandidate, TurnCredentials

MAX_SDP_LENGTH = 64 * 1024
MAX_CANDIDATES_PER_REQUEST = 50


class TurnCredentialsOut(BaseModel):
    urls: list[str]
    username: str
    credential: str
    expires_at: datetime

    @classmethod
    def of(cls, credentials: TurnCredentials) -> TurnCredentialsOut:
        return cls(
            urls=list(credentials.urls),
            username=credentials.username,
            credential=credentials.credential,
            expires_at=credentials.expires_at,
        )


class SessionOut(BaseModel):
    session_id: uuid.UUID
    device_id: uuid.UUID
    turn_credentials: TurnCredentialsOut
    created_at: datetime
    expires_at: datetime

    @classmethod
    def of(cls, session: StreamSession) -> SessionOut:
        return cls(
            session_id=session.id,
            device_id=session.device_id,
            turn_credentials=TurnCredentialsOut.of(session.turn_credentials),
            created_at=session.created_at,
            expires_at=session.expires_at,
        )


class OfferIn(BaseModel):
    session_id: uuid.UUID
    sdp: str = Field(min_length=1, max_length=MAX_SDP_LENGTH)


class AnswerIn(BaseModel):
    session_id: uuid.UUID
    sdp: str = Field(min_length=1, max_length=MAX_SDP_LENGTH)


class AnswerOut(BaseModel):
    session_id: uuid.UUID
    sdp: str


class PendingOfferOut(BaseModel):
    session_id: uuid.UUID
    sdp: str


class IceCandidateSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    candidate: str = Field(min_length=1, max_length=1024)
    sdp_mid: str | None = Field(default=None, alias="sdpMid", max_length=64)
    sdp_m_line_index: int | None = Field(default=None, alias="sdpMLineIndex", ge=0)

    @classmethod
    def of(cls, candidate: IceCandidate) -> IceCandidateSchema:
        return cls(
            candidate=candidate.candidate,
            sdp_mid=candidate.sdp_mid,
            sdp_m_line_index=candidate.sdp_m_line_index,
        )

    def to_domain(self) -> IceCandidate:
        return IceCandidate(
            sdp_mid=self.sdp_mid,
            sdp_m_line_index=self.sdp_m_line_index,
            candidate=self.candidate,
        )


class CandidatesIn(BaseModel):
    session_id: uuid.UUID
    # 上限擋住「一次塞爆 session」:candidate 會整包寫回 Redis,沒有上限等於讓
    # 任何持有 session 的人把 key 撐到記憶體用盡
    candidates: list[IceCandidateSchema] = Field(
        min_length=1, max_length=MAX_CANDIDATES_PER_REQUEST
    )


class CandidatesOut(BaseModel):
    candidates: list[IceCandidateSchema]
    next_since: int
