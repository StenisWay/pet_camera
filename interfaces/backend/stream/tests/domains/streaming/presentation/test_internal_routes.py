"""鏡頭端內部路由的 HTTP 契約(06_spec_即時串流.md 第 3.2 節)。"""

import asyncio

from httpx import AsyncClient

from app.domains.streaming.domain.entities import Peer, SignalingState
from tests.conftest import auth_header, camera_header
from tests.domains.streaming.builders import DEVICE_A, SESSION_A, a_candidate, a_session
from tests.domains.streaming.fakes import (
    FakeClock,
    FakeSignalingEvents,
    InMemoryStreamSessionRepository,
)

PENDING_OFFER_URL = f"/internal/devices/{DEVICE_A}/stream/pending-offer"
ANSWER_URL = f"/internal/devices/{DEVICE_A}/stream/answer"
CANDIDATES_URL = f"/internal/devices/{DEVICE_A}/stream/candidates"


def error_code(response) -> str:  # type: ignore[no-untyped-def]
    return response.json()["error"]["code"]


async def test_pending_offer_returns_the_waiting_offer(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))

    response = await client.get(PENDING_OFFER_URL, headers=camera_header())

    assert response.status_code == 200
    assert response.json() == {"session_id": str(SESSION_A), "sdp": "v=0 offer"}


async def test_long_poll_without_an_offer_is_204(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    """第 3.2 節:逾時 30 秒回 204(測試把門檻壓到毫秒)。"""
    await sessions.save(a_session())

    response = await client.get(PENDING_OFFER_URL, headers=camera_header())

    assert response.status_code == 204


async def test_internal_routes_reject_a_wrong_credential(client: AsyncClient) -> None:
    response = await client.get(PENDING_OFFER_URL, headers=camera_header("wrong"))

    assert response.status_code == 403


async def test_internal_routes_reject_a_viewer_token(client: AsyncClient) -> None:
    """使用者的 JWT 不能拿來走鏡頭端路由。"""
    response = await client.get(PENDING_OFFER_URL, headers=auth_header())

    assert response.status_code == 403


async def test_answer_is_accepted_and_stored(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))

    response = await client.post(
        ANSWER_URL,
        headers=camera_header(),
        json={"session_id": str(SESSION_A), "sdp": "v=0 answer"},
    )

    assert response.status_code == 204
    stored = await sessions.get(SESSION_A)
    assert stored is not None and stored.answer_sdp == "v=0 answer"


async def test_answer_for_a_dead_session_is_401(client: AsyncClient) -> None:
    response = await client.post(
        ANSWER_URL,
        headers=camera_header(),
        json={"session_id": str(SESSION_A), "sdp": "v=0 answer"},
    )

    assert response.status_code == 401
    assert error_code(response) == "STREAM_002"


async def test_camera_posts_and_reads_the_opposite_side_candidates(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository, clock: FakeClock
) -> None:
    session = a_session(state=SignalingState.OFFERED)
    session.add_candidate(Peer.VIEWER, a_candidate("viewer-1"), clock.now())
    await sessions.save(session)

    posted = await client.post(
        CANDIDATES_URL,
        headers=camera_header(),
        json={
            "session_id": str(SESSION_A),
            "candidates": [{"candidate": "camera-1", "sdpMid": "0", "sdpMLineIndex": 0}],
        },
    )
    fetched = await client.get(
        CANDIDATES_URL, headers=camera_header(), params={"session_id": str(SESSION_A), "since": 0}
    )

    assert posted.status_code == 204
    # 鏡頭端讀到的是觀看端送的,不是自己剛送的那一筆
    assert [c["candidate"] for c in fetched.json()["candidates"]] == ["viewer-1"]


async def test_offer_and_answer_can_cross_between_two_requests(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents
) -> None:
    """兩個請求同時在跑,正是 LB 把 offer 與 answer 分到不同複本的情境。

    觀看端送出 offer 後會阻塞等待;鏡頭端在同一個 event loop 裡輪詢、回覆,
    觀看端必須拿到那個 answer。
    """
    await sessions.save(a_session())

    async def camera_side() -> None:
        offer = await client.get(PENDING_OFFER_URL, headers=camera_header())
        assert offer.status_code == 200
        await client.post(
            ANSWER_URL,
            headers=camera_header(),
            json={"session_id": offer.json()["session_id"], "sdp": "v=0 answer"},
        )

    viewer = asyncio.create_task(
        client.post(
            f"/devices/{DEVICE_A}/stream/offer",
            headers=auth_header(),
            json={"session_id": str(SESSION_A), "sdp": "v=0 offer"},
        )
    )
    await asyncio.sleep(0)  # 讓觀看端先送出 offer 並開始等待
    await camera_side()
    response = await viewer

    assert response.status_code == 200
    assert response.json() == {"session_id": str(SESSION_A), "sdp": "v=0 answer"}
