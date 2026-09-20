"""StreamSession 的業務規則(06_spec_即時串流.md 第 2.4 節、第 7 節)。

業務規則在這一層窮盡;外層只驗證「規則有被接上」。
"""

from datetime import timedelta

import pytest

from app.domains.streaming.domain.entities import Peer, SignalingState, StreamSession
from app.domains.streaming.domain.exceptions import SessionExpired
from tests.domains.streaming.builders import (
    ALICE,
    BOB,
    DEVICE_A,
    NOW,
    SESSION_A,
    SESSION_TTL,
    a_candidate,
    a_session,
    turn_credentials,
)


def test_opened_session_expires_after_ttl() -> None:
    """第 2.4 節:session TTL 300 秒"""
    session = StreamSession.open(
        id=SESSION_A,
        device_id=DEVICE_A,
        owner_id=ALICE,
        turn_credentials=turn_credentials(),
        now=NOW,
        ttl=SESSION_TTL,
    )

    assert session.state is SignalingState.CREATED
    assert session.expires_at == NOW + SESSION_TTL


@pytest.mark.parametrize(
    ("elapsed", "expired"),
    [
        (timedelta(seconds=0), False),
        (timedelta(seconds=299), False),
        (timedelta(seconds=300), True),  # 邊界:到期當下即失效
        (timedelta(seconds=301), True),
    ],
)
def test_expiry_boundary(elapsed: timedelta, expired: bool) -> None:
    assert a_session().is_expired(NOW + elapsed) is expired


def test_session_is_owned_by_its_owner_only() -> None:
    """第 3.3 節:擁有者以外一律視為查無此裝置"""
    session = a_session(owner_id=ALICE)

    assert session.is_owned_by(ALICE) is True
    assert session.is_owned_by(BOB) is False


def test_submit_offer_moves_session_to_offered() -> None:
    session = a_session()

    session.submit_offer("v=0 offer", NOW)

    assert session.state is SignalingState.OFFERED
    assert session.offer_sdp == "v=0 offer"


def test_accept_answer_moves_session_to_answered() -> None:
    session = a_session(state=SignalingState.OFFERED)

    session.accept_answer("v=0 answer", NOW)

    assert session.state is SignalingState.ANSWERED
    assert session.answer_sdp == "v=0 answer"


@pytest.mark.parametrize(
    "action",
    [
        lambda s, now: s.submit_offer("v=0 offer", now),
        lambda s, now: s.accept_answer("v=0 answer", now),
        lambda s, now: s.add_candidate(Peer.VIEWER, None, now),
    ],
    ids=["submit_offer", "accept_answer", "add_candidate"],
)
def test_expired_session_rejects_all_signaling(action) -> None:
    """第 7 節 STREAM_002:帶著失效的 session_id 呼叫 signaling 一律拒絕"""
    session = a_session(state=SignalingState.OFFERED)
    after_expiry = NOW + SESSION_TTL

    with pytest.raises(SessionExpired):
        action(session, after_expiry)


def test_candidates_are_returned_per_peer_and_incrementally() -> None:
    """第 3.1/3.2 節:雙方各自輪詢對方的 candidate,以 since 取增量"""
    session = a_session(state=SignalingState.OFFERED)
    viewer_one, viewer_two = a_candidate("viewer-1"), a_candidate("viewer-2")
    camera_one = a_candidate("camera-1")

    session.add_candidate(Peer.VIEWER, viewer_one, NOW)
    session.add_candidate(Peer.VIEWER, viewer_two, NOW)
    session.add_candidate(Peer.CAMERA, camera_one, NOW)

    # 鏡頭端要讀的是觀看端送的,不是自己送的
    assert session.candidates_for(Peer.VIEWER, since=0) == [viewer_one, viewer_two]
    assert session.candidates_for(Peer.VIEWER, since=1) == [viewer_two]
    assert session.candidates_for(Peer.VIEWER, since=2) == []
    assert session.candidates_for(Peer.CAMERA, since=0) == [camera_one]


def test_resubmitting_offer_restarts_negotiation() -> None:
    """第 2.3 節:ICE 重連會重送 offer,舊的 answer 必須作廢,否則前端會收到過期的 answer"""
    session = a_session(state=SignalingState.ANSWERED)

    session.submit_offer("v=0 offer-2", NOW)

    assert session.state is SignalingState.OFFERED
    assert session.offer_sdp == "v=0 offer-2"
    assert session.answer_sdp is None
