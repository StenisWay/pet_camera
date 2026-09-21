"""觀看端 HTTP 契約(06_spec_即時串流.md 第 3.1 節、第 7 節錯誤碼表)。

這一層只測 HTTP 契約:狀態碼、錯誤碼、欄位形狀、限流有沒有掛上。
業務規則在 domain / application 已經測過,不在這裡重測。
"""

import uuid

from httpx import AsyncClient

from app.domains.streaming.domain.entities import Peer, SignalingState
from tests.conftest import auth_header
from tests.domains.streaming.builders import (
    BOB,
    DEVICE_A,
    SESSION_A,
    SESSION_TTL,
    a_candidate,
    a_session,
)
from tests.domains.streaming.fakes import (
    FakeClock,
    FakeDeviceDirectory,
    FakeRateLimitCounter,
    InMemoryStreamSessionRepository,
)

SESSION_URL = f"/devices/{DEVICE_A}/stream/session"
OFFER_URL = f"/devices/{DEVICE_A}/stream/offer"
CANDIDATES_URL = f"/devices/{DEVICE_A}/stream/candidates"


def error_code(response) -> str:  # type: ignore[no-untyped-def]
    return response.json()["error"]["code"]


async def test_open_session_returns_201_with_turn_credentials(client: AsyncClient) -> None:
    response = await client.post(SESSION_URL, headers=auth_header())

    assert response.status_code == 201
    body = response.json()
    assert body["session_id"] == str(SESSION_A)
    assert body["device_id"] == str(DEVICE_A)
    assert body["turn_credentials"]["urls"]
    assert body["turn_credentials"]["username"]
    assert body["turn_credentials"]["credential"]


async def test_open_session_requires_a_token(client: AsyncClient) -> None:
    response = await client.post(SESSION_URL)

    assert response.status_code == 401
    assert error_code(response) == "AUTH_001"


async def test_open_session_for_someone_elses_device_is_404(client: AsyncClient) -> None:
    """第 3.3 節:不回 403,不洩漏裝置存在性。"""
    response = await client.post(SESSION_URL, headers=auth_header(BOB))

    assert response.status_code == 404
    assert error_code(response) == "DEVICE_005"


async def test_open_session_for_an_offline_camera_is_409(
    client: AsyncClient, devices: FakeDeviceDirectory, clock: FakeClock
) -> None:
    """第 7 節 STREAM_001。"""
    clock.advance(SESSION_TTL)  # 心跳過期,超過 90 秒

    response = await client.post(SESSION_URL, headers=auth_header())

    assert response.status_code == 409
    assert error_code(response) == "STREAM_001"


async def test_second_session_takes_over_and_still_returns_201(client: AsyncClient) -> None:
    """第 2.4 節:接管,不回 STREAM_004。"""
    first = await client.post(SESSION_URL, headers=auth_header())
    second = await client.post(SESSION_URL, headers=auth_header())

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["session_id"] != second.json()["session_id"]


async def test_open_session_is_rate_limited(
    client: AsyncClient, rate_counter: FakeRateLimitCounter
) -> None:
    """規格審查 #10:每位使用者每分鐘 10 次,超過回 RATE_001。"""
    for _ in range(10):
        assert (await client.post(SESSION_URL, headers=auth_header())).status_code == 201

    response = await client.post(SESSION_URL, headers=auth_header())

    assert response.status_code == 429
    assert error_code(response) == "RATE_001"


async def test_signaling_endpoints_are_not_rate_limited(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    """ICE 協商期間 candidate 往返很密集,套「每分鐘 10 次」會把正常連線擋掉。"""
    await sessions.save(a_session(state=SignalingState.OFFERED))

    for _ in range(15):
        response = await client.post(
            CANDIDATES_URL,
            headers=auth_header(),
            json={"session_id": str(SESSION_A), "candidates": [{"candidate": "c", "sdpMid": "0"}]},
        )
        assert response.status_code == 204


async def test_offer_times_out_with_408(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    """第 7 節 STREAM_005 是 408——本專案唯一用到這個狀態碼的地方。"""
    await sessions.save(a_session())

    response = await client.post(
        OFFER_URL, headers=auth_header(), json={"session_id": str(SESSION_A), "sdp": "v=0 offer"}
    )

    assert response.status_code == 408
    assert error_code(response) == "STREAM_005"


async def test_offer_on_a_dead_session_is_401(client: AsyncClient) -> None:
    """第 7 節 STREAM_002 是 401,不是 409:前端要重建 session,不是處理狀態衝突。"""
    response = await client.post(
        OFFER_URL, headers=auth_header(), json={"session_id": str(SESSION_A), "sdp": "v=0 offer"}
    )

    assert response.status_code == 401
    assert error_code(response) == "STREAM_002"


async def test_malformed_body_is_400(client: AsyncClient) -> None:
    """10_錯誤處理與狀態規範.md 第 3 節:VAL_001 是 400,不是 FastAPI 預設的 422。"""
    response = await client.post(OFFER_URL, headers=auth_header(), json={"sdp": ""})

    assert response.status_code == 400
    assert error_code(response) == "VAL_001"


async def test_viewer_reads_camera_candidates_with_a_cursor(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository, clock: FakeClock
) -> None:
    session = a_session(state=SignalingState.OFFERED)
    session.add_candidate(Peer.CAMERA, a_candidate("camera-1"), clock.now())
    await sessions.save(session)

    response = await client.get(
        CANDIDATES_URL, headers=auth_header(), params={"session_id": str(SESSION_A), "since": 0}
    )

    assert response.status_code == 200
    body = response.json()
    assert [c["candidate"] for c in body["candidates"]] == ["camera-1"]
    assert body["next_since"] == 1
    # WebRTC 的欄位名原樣回傳,前端可以直接丟進 addIceCandidate
    assert "sdpMid" in body["candidates"][0]


async def test_delete_session_is_204_and_idempotent(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    await sessions.save(a_session())
    url = f"{SESSION_URL}/{SESSION_A}"

    assert (await client.delete(url, headers=auth_header())).status_code == 204
    assert (await client.delete(url, headers=auth_header())).status_code == 204


async def test_delete_of_an_unknown_session_is_204(client: AsyncClient) -> None:
    response = await client.delete(f"{SESSION_URL}/{uuid.uuid4()}", headers=auth_header())

    assert response.status_code == 204


async def test_delete_of_someone_elses_session_is_404(
    client: AsyncClient, sessions: InMemoryStreamSessionRepository
) -> None:
    await sessions.save(a_session())

    response = await client.delete(f"{SESSION_URL}/{SESSION_A}", headers=auth_header(BOB))

    assert response.status_code == 404
    assert error_code(response) == "DEVICE_005"
    assert await sessions.get(SESSION_A) is not None


async def test_health_does_not_touch_redis(client: AsyncClient) -> None:
    """13_ADR 第 3 節:VM-3 掛掉時不該讓兩台服務節點被判定為不健康。"""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
