"""結束直播 session(06_spec 第 3.1 節冪等、第 7 節 DELETE 的 fail-open 例外)。"""

import uuid

import pytest

from app.domains.streaming.application.use_cases.end_stream_session import EndStreamSession
from app.domains.streaming.domain.exceptions import DeviceNotFound
from app.shared_kernel.errors import ServiceUnavailable
from tests.domains.streaming.builders import ALICE, BOB, DEVICE_A, SESSION_A, a_session
from tests.domains.streaming.fakes import (
    InMemoryStreamSessionRepository,
    UnavailableStreamSessionRepository,
)


async def test_deleting_releases_the_device(
    sessions: InMemoryStreamSessionRepository,
) -> None:
    """驗收標準:離開直播頁後,鏡頭端與 TURN session 確實釋放。"""
    await sessions.save(a_session())

    await EndStreamSession(sessions).execute(
        device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE
    )

    assert await sessions.get(SESSION_A) is None
    assert await sessions.get_active_for_device(DEVICE_A) is None


async def test_deleting_twice_is_fine(sessions: InMemoryStreamSessionRepository) -> None:
    """第 3.1 節:冪等,一律 204。App 閃退後重開會再送一次 DELETE。"""
    await sessions.save(a_session())
    use_case = EndStreamSession(sessions)

    await use_case.execute(device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE)
    await use_case.execute(device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE)


async def test_deleting_an_unknown_session_is_fine(
    sessions: InMemoryStreamSessionRepository,
) -> None:
    await EndStreamSession(sessions).execute(
        device_id=DEVICE_A, session_id=uuid.uuid4(), requester_id=ALICE
    )


async def test_another_user_cannot_end_your_stream(
    sessions: InMemoryStreamSessionRepository,
) -> None:
    """第 3.3 節:DELETE 時 session_id 必須屬於呼叫者,否則 DEVICE_005。"""
    await sessions.save(a_session())

    with pytest.raises(DeviceNotFound):
        await EndStreamSession(sessions).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=BOB
        )

    assert await sessions.get(SESSION_A) is not None


async def test_store_outage_still_succeeds() -> None:
    """第 7 節例外:DELETE 採 fail-open。session 反正會因 TTL 消失,
    讓使用者在離開頁面時收到 503 沒有意義。"""
    await EndStreamSession(UnavailableStreamSessionRepository()).execute(
        device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE
    )


async def test_outage_while_deleting_still_succeeds(
    sessions: InMemoryStreamSessionRepository,
) -> None:
    """讀得到但刪不掉也是 fail-open:TTL 到了它自己會消失。"""

    class DeleteFails(InMemoryStreamSessionRepository):
        async def delete(self, session_id: uuid.UUID) -> None:
            raise ServiceUnavailable()

    failing = DeleteFails(sessions.clock)
    await failing.save(a_session())

    await EndStreamSession(failing).execute(
        device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE
    )
