"""歷史事件回放截圖(11_spec 第 2.1 節 + 審查 #5、#8、#13)。

與即時截圖的差別只在素材來源:這裡要先確認來源事件可用。
"""

from datetime import timedelta

import pytest

from app.domains.media.application.use_cases.take_event_screenshot import TakeEventScreenshot
from app.domains.media.domain.entities import MediaItemStatus
from app.domains.media.domain.exceptions import (
    ClipRangeInvalid,
    ClipSourceExpired,
    ClipSourceNotReady,
    MediaItemNotFound,
    ScreenshotSourceUnavailable,
)
from tests.domains.media.builders import (
    EVENT,
    EVENT_STARTED_AT,
    NOW,
    OTHER_USER,
    OWNER,
    an_event,
)
from tests.domains.media.fakes import (
    FakeEventSource,
    FakeFrameSource,
    FakeMediaStorage,
    FakeMediaUnitOfWork,
    FixedClock,
    SequentialIds,
)

RETENTION = timedelta(days=7)


@pytest.fixture
def uow():
    return FakeMediaUnitOfWork()


def build(uow, *, event=None, frames=None, storage=None):
    return TakeEventScreenshot(
        uow,
        FakeEventSource({EVENT: event} if event else {}),
        frames or FakeFrameSource(),
        storage or FakeMediaStorage(),
        FixedClock(NOW),
        SequentialIds(),
        retention=RETENTION,
    )


async def test_screenshot_records_the_source_event_and_its_moment(uow):
    """審查 #11:captured_at 取事件時間 + offset,不是按鈕按下的時間。"""
    frames = FakeFrameSource()
    use_case = build(uow, event=an_event(duration_sec=45), frames=frames)

    result = await use_case.execute(EVENT, offset_sec=10, requester_id=OWNER)

    assert result.status is MediaItemStatus.READY
    assert result.source_event_id == EVENT
    assert result.captured_at == EVENT_STARTED_AT + timedelta(seconds=10)
    assert frames.calls == [("event", EVENT, 10)]


async def test_unknown_event_is_reported_as_not_found(uow):
    use_case = build(uow, event=None)

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(EVENT, offset_sec=1, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_other_users_event_is_reported_as_not_found(uow):
    """審查 #6:不洩漏事件是否存在。"""
    use_case = build(uow, event=an_event(owner_id=OTHER_USER))

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(EVENT, offset_sec=1, requester_id=OWNER)

    assert uow.commit_count == 0


@pytest.mark.parametrize("status", ["processing", "failed"])
async def test_event_without_ready_video_cannot_be_captured(uow, status):
    """審查 #13:回放截圖套用與剪輯相同的來源前置條件。"""
    use_case = build(uow, event=an_event(status=status))

    with pytest.raises(ClipSourceNotReady):
        await use_case.execute(EVENT, offset_sec=1, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_event_past_retention_cannot_be_captured(uow):
    """審查 #8:videos/ 的 lifecycle 是 7 天,超過就沒有影片可擷幀。"""
    use_case = build(uow, event=an_event(started_at=NOW - RETENTION - timedelta(seconds=1)))

    with pytest.raises(ClipSourceExpired):
        await use_case.execute(EVENT, offset_sec=1, requester_id=OWNER)

    assert uow.commit_count == 0


@pytest.mark.parametrize("offset_sec", [-1, 46])
async def test_offset_outside_the_video_is_rejected(uow, offset_sec):
    """審查 #5:offset 以事件開始為基準,須落在 0..duration_sec 之間。"""
    use_case = build(uow, event=an_event(duration_sec=45))

    with pytest.raises(ClipRangeInvalid):
        await use_case.execute(EVENT, offset_sec=offset_sec, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_offset_at_the_last_second_is_allowed(uow):
    """邊界值:最後一秒仍可截圖。"""
    use_case = build(uow, event=an_event(duration_sec=45))

    result = await use_case.execute(EVENT, offset_sec=45, requester_id=OWNER)

    assert result.captured_at == EVENT_STARTED_AT + timedelta(seconds=45)


async def test_failed_capture_leaves_the_item_failed(uow):
    use_case = build(uow, event=an_event(), frames=FakeFrameSource(available=False))

    with pytest.raises(ScreenshotSourceUnavailable):
        await use_case.execute(EVENT, offset_sec=1, requester_id=OWNER)

    [item] = uow.media.committed.values()
    assert item.status is MediaItemStatus.FAILED
