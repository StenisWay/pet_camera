"""測試資料建構器與固定 ID。只寫出測試在乎的欄位,其餘給合理預設。"""

import uuid
from datetime import UTC, datetime, timedelta

from app.domains.streaming.domain.entities import SignalingState, StreamSession
from app.domains.streaming.domain.value_objects import IceCandidate, TurnCredentials

ALICE = uuid.UUID("00000000-0000-0000-0000-00000000a11c")
BOB = uuid.UUID("00000000-0000-0000-0000-00000000b0b0")
DEVICE_A = uuid.UUID("00000000-0000-0000-0000-0000000de71c")
SESSION_A = uuid.UUID("00000000-0000-0000-0000-000000005e51")

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
SESSION_TTL = timedelta(seconds=300)


def turn_credentials(*, expires_at: datetime | None = None) -> TurnCredentials:
    return TurnCredentials(
        urls=("turn:vm3.internal:3478?transport=udp",),
        username="1758369600:5e51",
        credential="dGVzdC1jcmVkZW50aWFs",
        expires_at=expires_at or (NOW + timedelta(seconds=600)),
    )


def a_session(
    *,
    id: uuid.UUID = SESSION_A,
    device_id: uuid.UUID = DEVICE_A,
    owner_id: uuid.UUID = ALICE,
    now: datetime = NOW,
    ttl: timedelta = SESSION_TTL,
    state: SignalingState = SignalingState.CREATED,
) -> StreamSession:
    session = StreamSession.open(
        id=id,
        device_id=device_id,
        owner_id=owner_id,
        turn_credentials=turn_credentials(),
        now=now,
        ttl=ttl,
    )
    if state is SignalingState.OFFERED:
        session.submit_offer("v=0 offer", now)
    elif state is SignalingState.ANSWERED:
        session.submit_offer("v=0 offer", now)
        session.accept_answer("v=0 answer", now)
    return session


DEFAULT_CANDIDATE = "candidate:1 1 udp 2130706431 10.0.0.1 54321 typ host"


def a_candidate(candidate: str = DEFAULT_CANDIDATE) -> IceCandidate:
    return IceCandidate(sdp_mid="0", sdp_m_line_index=0, candidate=candidate)
