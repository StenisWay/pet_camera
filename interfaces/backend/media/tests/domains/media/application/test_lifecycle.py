"""處理生命週期的收尾:worker 回呼與逾時掃描(審查 #3、#9)。

worker 沒有使用者身分,回呼時只知道 media_item_id——所以這幾個 use case 走的是
get_internal,而且只能掛在共享金鑰把關的內部端點上。
"""

from datetime import timedelta

import pytest

from app.domains.media.application.use_cases.expire_stale_processing import (
    ExpireStaleProcessing,
)
from app.domains.media.application.use_cases.finish_media_item import (
    CompleteMediaItem,
    FailMediaItem,
)
from app.domains.media.domain.entities import MediaItemStatus, MediaItemType
from app.domains.media.domain.exceptions import MediaItemNotFound, MediaItemNotProcessing
from tests.domains.media.builders import ITEM, NOW, OWNER, an_item
from tests.domains.media.fakes import FakeMediaUnitOfWork, FixedClock

STALE_AFTER = timedelta(minutes=15)


@pytest.fixture
def uow():
    return FakeMediaUnitOfWork()


async def test_worker_callback_publishes_the_clip(uow):
    """11_spec 第 2.2 節:轉檔完成後 status = ready,相簿即可播放。"""
    uow.given(an_item(type=MediaItemType.CLIP, status=MediaItemStatus.PROCESSING, duration_sec=15))
    use_case = CompleteMediaItem(uow, FixedClock(NOW))

    await use_case.execute(
        ITEM, object_key="media/a/x.mp4", thumbnail_object_key="media-thumbnails/a/x.jpg"
    )

    item = uow.media.committed[ITEM]
    assert item.status is MediaItemStatus.READY
    assert item.object_key == "media/a/x.mp4"
    assert uow.commit_count == 1


async def test_worker_callback_for_unknown_item_is_reported_as_not_found(uow):
    use_case = CompleteMediaItem(uow, FixedClock(NOW))

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(ITEM, object_key="media/a/x.mp4", thumbnail_object_key=None)

    assert uow.commit_count == 0


async def test_repeated_callback_does_not_revive_a_failed_item(uow):
    """worker 重試造成的重複回呼不該把 failed 翻回 ready(資料模型第 5 節)。"""
    uow.given(an_item(status=MediaItemStatus.FAILED))
    use_case = CompleteMediaItem(uow, FixedClock(NOW))

    with pytest.raises(MediaItemNotProcessing):
        await use_case.execute(ITEM, object_key="media/a/x.mp4", thumbnail_object_key=None)

    assert uow.media.committed[ITEM].status is MediaItemStatus.FAILED
    assert uow.commit_count == 0


async def test_worker_can_report_failure(uow):
    """CLIP_002:轉檔失敗,不建立可用內容。"""
    uow.given(an_item(status=MediaItemStatus.PROCESSING))
    use_case = FailMediaItem(uow, FixedClock(NOW))

    await use_case.execute(ITEM)

    assert uow.media.committed[ITEM].status is MediaItemStatus.FAILED


async def test_stuck_items_are_converged_to_failed(uow):
    """審查 #9:背景工作在無狀態複本上跑,複本被汰換後任務就消失了。

    與 F6 的 exporting 15 分鐘規則對稱,讓狀態機有終止保證。
    """
    stuck = uow.given(
        an_item(status=MediaItemStatus.PROCESSING, updated_at=NOW - timedelta(hours=1))
    )
    use_case = ExpireStaleProcessing(uow, FixedClock(NOW), stale_after=STALE_AFTER)

    expired = await use_case.execute()

    assert expired == 1
    assert uow.media.committed[stuck.id].status is MediaItemStatus.FAILED


async def test_recent_items_are_left_alone(uow):
    """還在正常處理中的項目不可被掃掉。"""
    uow.given(an_item(status=MediaItemStatus.PROCESSING, updated_at=NOW))
    use_case = ExpireStaleProcessing(uow, FixedClock(NOW), stale_after=STALE_AFTER)

    assert await use_case.execute() == 0
    assert uow.media.committed[ITEM].status is MediaItemStatus.PROCESSING


async def test_sweep_with_nothing_stuck_does_not_write(uow):
    """空掃描不該平白開一個交易。"""
    use_case = ExpireStaleProcessing(uow, FixedClock(NOW), stale_after=STALE_AFTER)

    assert await use_case.execute() == 0
    assert uow.commit_count == 0


async def test_sweep_ignores_ownership(uow):
    """逾時掃描是系統行為,不是使用者操作——不限擁有者。"""
    uow.given(
        an_item(
            owner_id=OWNER,
            status=MediaItemStatus.PROCESSING,
            updated_at=NOW - timedelta(hours=1),
        )
    )
    use_case = ExpireStaleProcessing(uow, FixedClock(NOW), stale_after=STALE_AFTER)

    assert await use_case.execute() == 1


async def test_failure_callback_for_unknown_item_is_reported_as_not_found(uow):
    """相簿項目可在處理中被刪除(12_spec 第 2.3 節),worker 可能拿著已消失的 id 回呼。"""
    use_case = FailMediaItem(uow, FixedClock(NOW))

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(ITEM)

    assert uow.commit_count == 0
