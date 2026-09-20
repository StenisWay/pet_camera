"""ICE candidate 交換(06_spec 第 3.1、3.2 節)。

增量規則本身在 domain 測過,這裡確認兩側讀到的是對方的 candidate、游標由後端算、
以及權限檢查沒有被漏掉。
"""

import uuid

import pytest

from app.domains.streaming.application.use_cases.exchange_candidates import (
    AddIceCandidates,
    FetchIceCandidates,
)
from app.domains.streaming.domain.entities import Peer, SignalingState
from app.domains.streaming.domain.exceptions import DeviceNotFound, SessionExpired
from tests.domains.streaming.builders import (
    ALICE,
    BOB,
    DEVICE_A,
    SESSION_A,
    SESSION_TTL,
    a_candidate,
    a_session,
)
from tests.domains.streaming.fakes import FakeClock, InMemoryStreamSessionRepository


@pytest.fixture
def add(sessions: InMemoryStreamSessionRepository, clock: FakeClock) -> AddIceCandidates:
    return AddIceCandidates(sessions, clock)


@pytest.fixture
def fetch(sessions: InMemoryStreamSessionRepository) -> FetchIceCandidates:
    return FetchIceCandidates(sessions)


async def test_each_side_reads_the_other_sides_candidates(
    sessions: InMemoryStreamSessionRepository, add: AddIceCandidates, fetch: FetchIceCandidates
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))
    await add.execute(
        device_id=DEVICE_A,
        session_id=SESSION_A,
        peer=Peer.VIEWER,
        candidates=[a_candidate("viewer-1")],
        requester_id=ALICE,
    )
    await add.execute(
        device_id=DEVICE_A,
        session_id=SESSION_A,
        peer=Peer.CAMERA,
        candidates=[a_candidate("camera-1")],
    )

    # 鏡頭端讀觀看端送的
    for_camera = await fetch.execute(
        device_id=DEVICE_A, session_id=SESSION_A, peer=Peer.VIEWER, since=0
    )
    # 觀看端讀鏡頭端送的
    for_viewer = await fetch.execute(
        device_id=DEVICE_A, session_id=SESSION_A, peer=Peer.CAMERA, since=0, requester_id=ALICE
    )

    assert for_camera.candidates == [a_candidate("viewer-1")]
    assert for_viewer.candidates == [a_candidate("camera-1")]


async def test_cursor_advances_so_the_client_never_computes_it(
    sessions: InMemoryStreamSessionRepository, add: AddIceCandidates, fetch: FetchIceCandidates
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))
    await add.execute(
        device_id=DEVICE_A,
        session_id=SESSION_A,
        peer=Peer.CAMERA,
        candidates=[a_candidate("camera-1"), a_candidate("camera-2")],
    )

    first = await fetch.execute(
        device_id=DEVICE_A, session_id=SESSION_A, peer=Peer.CAMERA, since=0, requester_id=ALICE
    )
    assert first.next_since == 2

    again = await fetch.execute(
        device_id=DEVICE_A,
        session_id=SESSION_A,
        peer=Peer.CAMERA,
        since=first.next_since,
        requester_id=ALICE,
    )
    assert again.candidates == []
    assert again.next_since == 2


async def test_candidates_survive_the_round_trip_through_storage(
    sessions: InMemoryStreamSessionRepository, add: AddIceCandidates
) -> None:
    """add 之後必須 save,否則 candidate 只存在這個複本的記憶體裡。"""
    await sessions.save(a_session(state=SignalingState.OFFERED))

    await add.execute(
        device_id=DEVICE_A,
        session_id=SESSION_A,
        peer=Peer.VIEWER,
        candidates=[a_candidate("viewer-1")],
        requester_id=ALICE,
    )

    stored = await sessions.get(SESSION_A)
    assert stored is not None
    assert stored.candidates_for(Peer.VIEWER, since=0) == [a_candidate("viewer-1")]


async def test_expired_session_rejects_candidates(
    sessions: InMemoryStreamSessionRepository, add: AddIceCandidates, clock: FakeClock
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))
    clock.advance(SESSION_TTL)

    with pytest.raises(SessionExpired):
        await add.execute(
            device_id=DEVICE_A,
            session_id=SESSION_A,
            peer=Peer.VIEWER,
            candidates=[a_candidate()],
            requester_id=ALICE,
        )


async def test_another_user_cannot_inject_candidates(
    sessions: InMemoryStreamSessionRepository, add: AddIceCandidates
) -> None:
    """規格審查 #3:candidate 端點同樣要驗擁有者,否則任何人都能污染別人的協商。"""
    await sessions.save(a_session(state=SignalingState.OFFERED))

    with pytest.raises(DeviceNotFound):
        await add.execute(
            device_id=DEVICE_A,
            session_id=SESSION_A,
            peer=Peer.VIEWER,
            candidates=[a_candidate()],
            requester_id=BOB,
        )


async def test_another_user_cannot_read_candidates(
    sessions: InMemoryStreamSessionRepository, fetch: FetchIceCandidates
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))

    with pytest.raises(DeviceNotFound):
        await fetch.execute(
            device_id=DEVICE_A,
            session_id=SESSION_A,
            peer=Peer.CAMERA,
            since=0,
            requester_id=BOB,
        )


async def test_candidates_for_a_session_of_another_device_are_rejected(
    sessions: InMemoryStreamSessionRepository, fetch: FetchIceCandidates
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))

    with pytest.raises(DeviceNotFound):
        await fetch.execute(
            device_id=uuid.uuid4(), session_id=SESSION_A, peer=Peer.VIEWER, since=0
        )
