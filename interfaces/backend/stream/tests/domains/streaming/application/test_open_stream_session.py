"""建立直播 session(06_spec 第 2.1、2.4 節,第 7 節 STREAM_001 / DEVICE_005)。

業務規則本身在 domain 測試窮盡,這裡測的是流程編排有沒有把規則接上。
"""

import uuid
from datetime import timedelta

import pytest

from app.domains.streaming.application.use_cases.open_stream_session import OpenStreamSession
from app.domains.streaming.domain.entities import SignalingState
from app.domains.streaming.domain.exceptions import DeviceNotFound, DeviceOffline
from app.domains.streaming.domain.value_objects import DeviceStatus
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.streaming.builders import (
    ALICE,
    BOB,
    DEVICE_A,
    NOW,
    SESSION_A,
    SESSION_TTL,
    a_device,
)
from tests.domains.streaming.fakes import (
    FakeClock,
    FakeDeviceDirectory,
    FakeTurnCredentialIssuer,
    FixedIdGenerator,
    InMemoryStreamSessionRepository,
)

SECOND_SESSION = uuid.UUID("00000000-0000-0000-0000-000000005e52")


@pytest.fixture
def use_case(
    sessions: InMemoryStreamSessionRepository,
    devices: FakeDeviceDirectory,
    turn: FakeTurnCredentialIssuer,
    clock: FakeClock,
) -> OpenStreamSession:
    return OpenStreamSession(
        sessions,
        devices,
        turn,
        clock,
        FixedIdGenerator(SESSION_A, SECOND_SESSION),
        ttl=SESSION_TTL,
    )


async def test_creates_session_with_turn_credentials(
    use_case: OpenStreamSession, sessions: InMemoryStreamSessionRepository
) -> None:
    session = await use_case.execute(DEVICE_A, ALICE)

    assert session.id == SESSION_A
    assert session.device_id == DEVICE_A
    assert session.owner_id == ALICE
    assert session.state is SignalingState.CREATED
    assert session.expires_at == NOW + SESSION_TTL
    assert await sessions.get(SESSION_A) is not None


async def test_turn_credentials_outlive_the_session(use_case: OpenStreamSession) -> None:
    """第 2.5 節:憑證效期(600s)刻意長於 session TTL(300s),
    不會出現 session 還在、TURN 憑證先過期的狀態。"""
    session = await use_case.execute(DEVICE_A, ALICE)

    assert session.turn_credentials.expires_at > session.expires_at


async def test_offline_device_is_rejected_before_anything_is_created(
    sessions: InMemoryStreamSessionRepository,
    turn: FakeTurnCredentialIssuer,
    clock: FakeClock,
) -> None:
    """第 7 節 STREAM_001。驗收標準:離線時不發起 WebRTC 流程,所以連憑證都不該簽。"""
    use_case = OpenStreamSession(
        sessions,
        FakeDeviceDirectory(a_device(status=DeviceStatus.OFFLINE)),
        turn,
        clock,
        FixedIdGenerator(SESSION_A),
        ttl=SESSION_TTL,
    )

    with pytest.raises(DeviceOffline):
        await use_case.execute(DEVICE_A, ALICE)

    assert turn.issued_for == []
    assert await sessions.get_active_for_device(DEVICE_A) is None


async def test_stale_heartbeat_counts_as_offline(
    sessions: InMemoryStreamSessionRepository,
    turn: FakeTurnCredentialIssuer,
    clock: FakeClock,
) -> None:
    """規格審查 #7:沒有人把 paired 轉成 offline,所以 Stream 自己看心跳新鮮度。"""
    use_case = OpenStreamSession(
        sessions,
        FakeDeviceDirectory(a_device(last_seen_ago=timedelta(seconds=120))),
        turn,
        clock,
        FixedIdGenerator(SESSION_A),
        ttl=SESSION_TTL,
    )

    with pytest.raises(DeviceOffline):
        await use_case.execute(DEVICE_A, ALICE)


async def test_other_users_device_looks_like_it_does_not_exist(
    use_case: OpenStreamSession,
) -> None:
    """第 3.3 節:不屬於呼叫者回 DEVICE_005(404),不回 403。"""
    with pytest.raises(DeviceNotFound):
        await use_case.execute(DEVICE_A, BOB)


async def test_unknown_device_is_device_not_found(use_case: OpenStreamSession) -> None:
    with pytest.raises(DeviceNotFound):
        await use_case.execute(uuid.uuid4(), ALICE)


async def test_unpaired_device_is_device_not_found(
    sessions: InMemoryStreamSessionRepository,
    turn: FakeTurnCredentialIssuer,
    clock: FakeClock,
) -> None:
    """pending 裝置沒有擁有者,任何人都不該串流它。"""
    use_case = OpenStreamSession(
        sessions,
        FakeDeviceDirectory(a_device(status=DeviceStatus.PENDING, owner_id=None)),
        turn,
        clock,
        FixedIdGenerator(SESSION_A),
        ttl=SESSION_TTL,
    )

    with pytest.raises(DeviceNotFound):
        await use_case.execute(DEVICE_A, ALICE)


async def test_second_session_takes_over_the_first(
    use_case: OpenStreamSession, sessions: InMemoryStreamSessionRepository
) -> None:
    """第 2.4 節:同一擁有者再建一次直接接管,回 201,不回 STREAM_004。"""
    first = await use_case.execute(DEVICE_A, ALICE)
    second = await use_case.execute(DEVICE_A, ALICE)

    assert second.id != first.id
    assert await sessions.get(first.id) is None
    active = await sessions.get_active_for_device(DEVICE_A)
    assert active is not None and active.id == second.id


async def test_device_service_outage_fails_closed(
    sessions: InMemoryStreamSessionRepository,
    turn: FakeTurnCredentialIssuer,
    clock: FakeClock,
) -> None:
    """13_ADR 第 4 節:Stream 選一致性。查不到裝置狀態時寧可失敗,
    不假設它在線上——連到錯誤的裝置狀態比連線失敗糟。"""
    use_case = OpenStreamSession(
        sessions,
        FakeDeviceDirectory(unavailable=True),
        turn,
        clock,
        FixedIdGenerator(SESSION_A),
        ttl=SESSION_TTL,
    )

    with pytest.raises(ServiceUnavailable):
        await use_case.execute(DEVICE_A, ALICE)
