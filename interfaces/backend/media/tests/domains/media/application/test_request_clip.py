"""剪輯請求的編排(11_spec 第 2.2 節 + 審查 #3、#4、#10)。

剪輯是非同步的:本服務只負責檢核、落地 processing 紀錄、派工給 VM-3 的 worker,
轉碼完成後由 worker 回呼內部端點推進狀態。
"""

from datetime import timedelta

import pytest

from app.domains.media.application.use_cases.request_clip import RequestClip
from app.domains.media.domain.entities import MediaItemStatus, MediaItemType
from app.domains.media.domain.exceptions import (
    ClipDispatchFailed,
    ClipRangeInvalid,
    ClipSourceExpired,
    ClipSourceNotReady,
    ClipTooLong,
    MediaItemNotFound,
)
from app.domains.media.domain.object_keys import content_key, thumbnail_key
from tests.domains.media.builders import (
    EVENT,
    EVENT_STARTED_AT,
    NOW,
    OTHER_USER,
    OWNER,
    an_event,
)
from tests.domains.media.fakes import (
    FakeClipWorker,
    FakeEventSource,
    FakeMediaUnitOfWork,
    FixedClock,
    SequentialIds,
)

RETENTION = timedelta(days=7)


@pytest.fixture
def uow():
    return FakeMediaUnitOfWork()


@pytest.fixture
def worker():
    return FakeClipWorker()


def build(uow, worker, *, event=None):
    return RequestClip(
        uow,
        FakeEventSource({EVENT: event} if event else {}),
        worker,
        FixedClock(NOW),
        SequentialIds(),
        retention=RETENTION,
    )


async def test_accepted_clip_is_recorded_as_processing_and_dispatched(uow, worker):
    """11_spec 第 2.2 節:受理後背景處理,前端停留在當前頁面。"""
    use_case = build(uow, worker, event=an_event(duration_sec=45))

    result = await use_case.execute(EVENT, start_sec=10, end_sec=25, requester_id=OWNER)

    assert result.status is MediaItemStatus.PROCESSING
    assert result.type is MediaItemType.CLIP
    assert result.duration_sec == 15
    assert result.captured_at == EVENT_STARTED_AT + timedelta(seconds=10)  # 審查 #11
    assert uow.commit_count == 1
    [job] = worker.dispatched
    assert job["source_event_id"] == EVENT
    assert (job["start_sec"], job["end_sec"]) == (10, 25)


async def test_dispatched_job_carries_the_keys_the_worker_should_write_to(uow, worker):
    """key 由本服務算(資料模型 §3.1),不讓 worker 自己決定放哪裡。"""
    use_case = build(uow, worker, event=an_event(duration_sec=45))

    result = await use_case.execute(EVENT, start_sec=0, end_sec=15, requester_id=OWNER)

    [item] = uow.media.committed.values()
    [job] = worker.dispatched
    assert job["media_item_id"] == result.id
    assert job["object_key"] == content_key(item)
    assert job["thumbnail_object_key"] == thumbnail_key(item)


async def test_resending_the_same_range_returns_the_existing_clip(uow, worker):
    """審查 #10:前端 disable 按鈕不是防護,連點與網路重試都會重送。

    重複受理會在相簿產生兩個一模一樣的項目,也會讓 VM-3 白做一次轉碼。
    """
    use_case = build(uow, worker, event=an_event(duration_sec=45))

    first = await use_case.execute(EVENT, start_sec=10, end_sec=25, requester_id=OWNER)
    second = await use_case.execute(EVENT, start_sec=10, end_sec=25, requester_id=OWNER)

    assert second.id == first.id
    assert len(uow.media.committed) == 1
    assert len(worker.dispatched) == 1


async def test_a_different_range_of_the_same_event_is_a_new_clip(uow, worker):
    use_case = build(uow, worker, event=an_event(duration_sec=45))

    first = await use_case.execute(EVENT, start_sec=10, end_sec=25, requester_id=OWNER)
    second = await use_case.execute(EVENT, start_sec=10, end_sec=30, requester_id=OWNER)

    assert second.id != first.id
    assert len(worker.dispatched) == 2


async def test_failed_dispatch_leaves_the_item_failed(uow):
    """worker 連不上時項目要收斂成 failed,不可留在 processing 等 15 分鐘逾時。"""
    use_case = build(uow, FakeClipWorker(available=False), event=an_event(duration_sec=45))

    with pytest.raises(ClipDispatchFailed):
        await use_case.execute(EVENT, start_sec=0, end_sec=15, requester_id=OWNER)

    [item] = uow.media.committed.values()
    assert item.status is MediaItemStatus.FAILED


async def test_unknown_event_is_reported_as_not_found(uow, worker):
    use_case = build(uow, worker, event=None)

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(EVENT, start_sec=0, end_sec=15, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_other_users_event_is_reported_as_not_found(uow, worker):
    """審查 #6:IDOR。"""
    use_case = build(uow, worker, event=an_event(owner_id=OTHER_USER))

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(EVENT, start_sec=0, end_sec=15, requester_id=OWNER)

    assert uow.commit_count == 0
    assert worker.dispatched == []


async def test_expired_source_cannot_be_clipped(uow, worker):
    """CLIP_001(審查 #8):保留期 7 天,以 started_at 推算。"""
    expired = an_event(started_at=NOW - RETENTION - timedelta(seconds=1))
    use_case = build(uow, worker, event=expired)

    with pytest.raises(ClipSourceExpired):
        await use_case.execute(EVENT, start_sec=0, end_sec=15, requester_id=OWNER)

    assert uow.commit_count == 0


@pytest.mark.parametrize("status", ["processing", "failed"])
async def test_source_without_ready_video_cannot_be_clipped(uow, worker, status):
    """11_spec 第 2.2 節:僅能剪輯 status = ready 的事件影片。"""
    use_case = build(uow, worker, event=an_event(status=status))

    with pytest.raises(ClipSourceNotReady):
        await use_case.execute(EVENT, start_sec=0, end_sec=15, requester_id=OWNER)


async def test_clip_longer_than_the_limit_is_rejected(uow, worker):
    """CLIP_003(審查 #4):上限 60 秒,對齊 F2 的單一事件錄影上限。"""
    use_case = build(uow, worker, event=an_event(duration_sec=45))

    with pytest.raises(ClipTooLong):
        await use_case.execute(EVENT, start_sec=0, end_sec=61, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_range_beyond_the_source_video_is_rejected(uow, worker):
    """11_spec 第 2.2 節:不支援跨事件合併剪輯(審查 #14:回 VAL_001)。"""
    use_case = build(uow, worker, event=an_event(duration_sec=45))

    with pytest.raises(ClipRangeInvalid):
        await use_case.execute(EVENT, start_sec=40, end_sec=50, requester_id=OWNER)

    assert uow.commit_count == 0
