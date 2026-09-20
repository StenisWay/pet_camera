"""完整直播流程走一遍 HTTP(06_spec_即時串流.md 第 2.1 節與第 8 節驗收標準)。

只用對外的 HTTP 介面,不碰內部物件——這是唯一會同時踩到觀看端與鏡頭端兩條路徑的測試。
外部系統(Redis / TURN / Device 服務)仍是 fake,見 tests/conftest.py。
"""

import asyncio

from httpx import AsyncClient

from tests.conftest import auth_header, camera_header
from tests.domains.streaming.builders import DEVICE_A

SESSION_URL = f"/devices/{DEVICE_A}/stream/session"
OFFER_URL = f"/devices/{DEVICE_A}/stream/offer"
VIEWER_CANDIDATES_URL = f"/devices/{DEVICE_A}/stream/candidates"
CAMERA_BASE = f"/internal/devices/{DEVICE_A}/stream"


async def test_full_streaming_session(client: AsyncClient) -> None:
    # 1. 觀看端開啟直播頁,取得 session 與 TURN 憑證
    opened = await client.post(SESSION_URL, headers=auth_header())
    assert opened.status_code == 201
    session_id = opened.json()["session_id"]

    # 2. 觀看端送出 offer 並阻塞等待;鏡頭端同時在長輪詢
    async def camera_completes_signaling() -> None:
        offer = await client.get(f"{CAMERA_BASE}/pending-offer", headers=camera_header())
        assert offer.status_code == 200
        assert offer.json()["sdp"] == "v=0 viewer-offer"
        answered = await client.post(
            f"{CAMERA_BASE}/answer",
            headers=camera_header(),
            json={"session_id": session_id, "sdp": "v=0 camera-answer"},
        )
        assert answered.status_code == 204

    viewer_offer = asyncio.create_task(
        client.post(
            OFFER_URL,
            headers=auth_header(),
            json={"session_id": session_id, "sdp": "v=0 viewer-offer"},
        )
    )
    await asyncio.sleep(0)
    await camera_completes_signaling()
    answer = await viewer_offer

    assert answer.status_code == 200
    assert answer.json()["sdp"] == "v=0 camera-answer"

    # 3. 雙方交換 ICE candidate,各自只讀到對方送的
    await client.post(
        VIEWER_CANDIDATES_URL,
        headers=auth_header(),
        json={
            "session_id": session_id,
            "candidates": [{"candidate": "viewer-1", "sdpMid": "0", "sdpMLineIndex": 0}],
        },
    )
    await client.post(
        f"{CAMERA_BASE}/candidates",
        headers=camera_header(),
        json={
            "session_id": session_id,
            "candidates": [{"candidate": "camera-1", "sdpMid": "0", "sdpMLineIndex": 0}],
        },
    )

    for_viewer = await client.get(
        VIEWER_CANDIDATES_URL, headers=auth_header(), params={"session_id": session_id, "since": 0}
    )
    for_camera = await client.get(
        f"{CAMERA_BASE}/candidates",
        headers=camera_header(),
        params={"session_id": session_id, "since": 0},
    )

    assert [c["candidate"] for c in for_viewer.json()["candidates"]] == ["camera-1"]
    assert [c["candidate"] for c in for_camera.json()["candidates"]] == ["viewer-1"]

    # 4. 離開直播頁,資源釋放(第 8 節驗收標準)
    ended = await client.delete(f"{SESSION_URL}/{session_id}", headers=auth_header())
    assert ended.status_code == 204

    stale = await client.post(
        OFFER_URL, headers=auth_header(), json={"session_id": session_id, "sdp": "v=0 again"}
    )
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "STREAM_002"


async def test_second_viewer_takes_over_and_the_first_is_cut_off(client: AsyncClient) -> None:
    """第 8 節驗收標準:同一位擁有者的第二個觀看端連線時,舊連線被接管中斷。"""
    first = await client.post(SESSION_URL, headers=auth_header())
    second = await client.post(SESSION_URL, headers=auth_header())

    assert second.status_code == 201

    old_session = first.json()["session_id"]
    cut_off = await client.post(
        OFFER_URL, headers=auth_header(), json={"session_id": old_session, "sdp": "v=0 offer"}
    )

    assert cut_off.status_code == 401
    assert cut_off.json()["error"]["code"] == "STREAM_002"

    # 新的那條還活著:鏡頭端輪詢看得到它的 offer
    new_session = second.json()["session_id"]

    async def camera_answers() -> None:
        offer = await client.get(f"{CAMERA_BASE}/pending-offer", headers=camera_header())
        assert offer.json()["session_id"] == new_session
        await client.post(
            f"{CAMERA_BASE}/answer",
            headers=camera_header(),
            json={"session_id": new_session, "sdp": "v=0 answer"},
        )

    pending = asyncio.create_task(
        client.post(
            OFFER_URL, headers=auth_header(), json={"session_id": new_session, "sdp": "v=0 offer"}
        )
    )
    await asyncio.sleep(0)
    await camera_answers()

    assert (await pending).status_code == 200
