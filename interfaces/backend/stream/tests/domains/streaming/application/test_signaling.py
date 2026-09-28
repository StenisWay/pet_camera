"""SDP 交換:offer / answer / 待處理 offer 長輪詢(06_spec 第 3.1、3.2 節)。

這一層測的是兩個複本之間的編排——存了才通知、等不到就逾時、等待期間被接管要看得出來。
"""

import uuid

import pytest

from app.domains.streaming.application.use_cases.answer_offer import AnswerOffer
from app.domains.streaming.application.use_cases.fetch_pending_offer import FetchPendingOffer
from app.domains.streaming.application.use_cases.submit_offer import SubmitOffer
from app.domains.streaming.domain.entities import SignalingState
from app.domains.streaming.domain.exceptions import (
    DeviceNotFound,
    SessionExpired,
    SignalingTimeout,
)
from tests.domains.streaming.application.conftest import FAST_TIMEOUT
from tests.domains.streaming.builders import (
    ALICE,
    BOB,
    DEVICE_A,
    SESSION_A,
    SESSION_TTL,
    a_session,
)
from tests.domains.streaming.fakes import (
    FakeClock,
    FakeSignalingEvents,
    InMemoryStreamSessionRepository,
)

OTHER_DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000de72c")


def submit_offer(
    sessions: InMemoryStreamSessionRepository,
    events: FakeSignalingEvents,
    clock: FakeClock,
) -> SubmitOffer:
    return SubmitOffer(sessions, events, clock, answer_timeout=FAST_TIMEOUT)


# ---------------------------------------------------------------- 觀看端 offer


async def test_offer_returns_the_answer_written_by_the_camera(
    sessions: InMemoryStreamSessionRepository, clock: FakeClock
) -> None:
    """鏡頭端的 answer 很可能寫在另一台複本上,所以 answer 必須重讀,
    不能用送出 offer 時手上那份 session。"""
    await sessions.save(a_session())

    async def camera_answers(session_id: uuid.UUID) -> None:
        await AnswerOffer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=session_id, sdp="v=0 answer"
        )

    events = FakeSignalingEvents(on_wait_for_answer=camera_answers)

    answer = await submit_offer(sessions, events, clock).execute(
        device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
    )

    assert answer == "v=0 answer"
    assert events.announced_offers == [DEVICE_A]
    assert events.announced_answers == [SESSION_A]


async def test_offer_is_persisted_before_the_camera_is_notified(
    sessions: InMemoryStreamSessionRepository, clock: FakeClock
) -> None:
    """先存再通知。反過來的話,被喚醒的另一個複本會讀到還沒寫入 offer 的 session。"""
    await sessions.save(a_session())
    seen: list[str | None] = []

    async def camera_polls(device_id: uuid.UUID) -> None:
        stored = await sessions.get_active_for_device(device_id)
        seen.append(stored.offer_sdp if stored else None)

    events = FakeSignalingEvents(on_wait_for_answer=lambda _sid: camera_polls(DEVICE_A))

    with pytest.raises(SignalingTimeout):
        await submit_offer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
        )

    assert seen == ["v=0 offer"]


async def test_offer_times_out_when_the_camera_never_answers(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    """第 3.1 節:等 answer 超過 5 秒 -> STREAM_005(408)。"""
    await sessions.save(a_session())

    with pytest.raises(SignalingTimeout):
        await submit_offer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
        )


async def test_session_taken_over_while_waiting_is_reported_as_expired(
    sessions: InMemoryStreamSessionRepository, clock: FakeClock
) -> None:
    """等待期間被別台裝置接管:前端要收到 STREAM_002 重新建立 session,
    而不是 STREAM_005 的「再重試一次 offer」——重試永遠不會成功。"""
    await sessions.save(a_session())

    async def taken_over(session_id: uuid.UUID) -> None:
        await sessions.save(a_session(id=uuid.uuid4()))
        await events.announce_answer(session_id)

    events = FakeSignalingEvents(on_wait_for_answer=taken_over)

    with pytest.raises(SessionExpired):
        await submit_offer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
        )


async def test_offer_on_unknown_session_is_session_expired(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    """第 7 節 STREAM_002:帶著失效的 session_id 呼叫。"""
    with pytest.raises(SessionExpired):
        await submit_offer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
        )


async def test_offer_on_expired_session_is_session_expired(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    await sessions.save(a_session())
    clock.advance(SESSION_TTL)

    with pytest.raises(SessionExpired):
        await submit_offer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
        )


async def test_offer_on_someone_elses_session_looks_like_a_missing_device(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    """規格審查 #3 的 IDOR:別人的 session_id 不能拿來推進 signaling。"""
    await sessions.save(a_session(owner_id=ALICE))

    with pytest.raises(DeviceNotFound):
        await submit_offer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, requester_id=BOB, sdp="v=0 offer"
        )


async def test_offer_with_mismatched_device_is_rejected(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    """session 掛在別的裝置底下:路徑上的 device_id 與 session 必須是同一支鏡頭。"""
    await sessions.save(a_session())

    with pytest.raises(DeviceNotFound):
        await submit_offer(sessions, events, clock).execute(
            device_id=OTHER_DEVICE, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
        )


# ---------------------------------------------------------------- 鏡頭端 answer


async def test_answer_marks_the_session_answered(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    await sessions.save(a_session(state=SignalingState.OFFERED))

    await AnswerOffer(sessions, events, clock).execute(
        device_id=DEVICE_A, session_id=SESSION_A, sdp="v=0 answer"
    )

    stored = await sessions.get(SESSION_A)
    assert stored is not None
    assert stored.state is SignalingState.ANSWERED
    assert stored.answer_sdp == "v=0 answer"


async def test_answer_for_a_dead_session_is_session_expired(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    """鏡頭拿著被接管掉的 session 回覆 answer,不該把它復活。"""
    with pytest.raises(SessionExpired):
        await AnswerOffer(sessions, events, clock).execute(
            device_id=DEVICE_A, session_id=SESSION_A, sdp="v=0 answer"
        )


async def test_answer_for_another_devices_session_is_rejected(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents, clock: FakeClock
) -> None:
    """一支鏡頭不能回覆另一支鏡頭的 session。"""
    await sessions.save(a_session(state=SignalingState.OFFERED))

    with pytest.raises(DeviceNotFound):
        await AnswerOffer(sessions, events, clock).execute(
            device_id=OTHER_DEVICE, session_id=SESSION_A, sdp="v=0 answer"
        )


# -------------------------------------------------------- 鏡頭端待處理 offer 輪詢


def pending_offer(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents
) -> FetchPendingOffer:
    return FetchPendingOffer(sessions, events, poll_timeout=FAST_TIMEOUT)


async def test_pending_offer_already_waiting_is_returned_without_blocking(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents
) -> None:
    """offer 可能在鏡頭重新發起輪詢之前就送到了。只等通知會讓鏡頭空轉一整輪。"""
    await sessions.save(a_session(state=SignalingState.OFFERED))

    result = await pending_offer(sessions, events).execute(DEVICE_A)

    assert result is not None
    assert result.session_id == SESSION_A
    assert result.sdp == "v=0 offer"
    assert events.offer_waits == []


async def test_pending_offer_arriving_during_the_long_poll_is_returned(
    sessions: InMemoryStreamSessionRepository,
) -> None:
    async def offer_arrives(device_id: uuid.UUID) -> None:
        await sessions.save(a_session(state=SignalingState.OFFERED))
        await events.announce_offer(device_id)

    events = FakeSignalingEvents(on_wait_for_offer=offer_arrives)
    await sessions.save(a_session())

    result = await pending_offer(sessions, events).execute(DEVICE_A)

    assert result is not None and result.sdp == "v=0 offer"


async def test_long_poll_without_an_offer_returns_none(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents
) -> None:
    """第 3.2 節:逾時 30 秒回 204。"""
    await sessions.save(a_session())

    assert await pending_offer(sessions, events).execute(DEVICE_A) is None
    assert events.offer_waits == [(DEVICE_A, FAST_TIMEOUT)]


async def test_already_answered_offer_is_not_pending(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents
) -> None:
    """否則鏡頭每一輪都會拿到同一個 offer,無止盡重新協商。"""
    await sessions.save(a_session(state=SignalingState.ANSWERED))

    assert await pending_offer(sessions, events).execute(DEVICE_A) is None


async def test_no_session_at_all_returns_none(
    sessions: InMemoryStreamSessionRepository, events: FakeSignalingEvents
) -> None:
    assert await pending_offer(sessions, events).execute(DEVICE_A) is None


# ------------------------------------------------- Pub/Sub 不補送:通知遺失的情況


async def test_answer_is_found_even_when_the_notification_is_lost(
    sessions: InMemoryStreamSessionRepository, clock: FakeClock
) -> None:
    """Redis Pub/Sub 不補送:answer 若在觀看端訂閱之前就發布,通知收不到。

    逾時後必須再讀一次 Redis,否則明明已經協商成功,前端卻收到 STREAM_005
    再白跑一輪。
    """
    await sessions.save(a_session())

    async def camera_answers_without_notifying(session_id: uuid.UUID) -> None:
        stored = await sessions.get(session_id)
        assert stored is not None
        stored.accept_answer("v=0 answer", clock.now())
        await sessions.save(stored)

    events = FakeSignalingEvents(on_wait_for_answer=camera_answers_without_notifying)

    answer = await submit_offer(sessions, events, clock).execute(
        device_id=DEVICE_A, session_id=SESSION_A, requester_id=ALICE, sdp="v=0 offer"
    )

    assert answer == "v=0 answer"
    assert events.announced_answers == []


async def test_pending_offer_is_found_even_when_the_notification_is_lost(
    sessions: InMemoryStreamSessionRepository,
) -> None:
    async def offer_arrives_without_notifying(device_id: uuid.UUID) -> None:
        await sessions.save(a_session(state=SignalingState.OFFERED))

    events = FakeSignalingEvents(on_wait_for_offer=offer_arrives_without_notifying)
    await sessions.save(a_session())

    result = await pending_offer(sessions, events).execute(DEVICE_A)

    assert result is not None and result.sdp == "v=0 offer"
    assert events.announced_offers == []
