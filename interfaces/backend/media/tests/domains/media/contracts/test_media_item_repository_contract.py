"""MediaItemRepository 的行為承諾,每個實作都要通過。

內容逐條來自 domain/repositories.py 的 docstring。為什麼重要:application 層的測試
全部建立在 fake 上,fake 若與正式實作行為不同(例如 get 回傳同一個物件、修改不用
save 就生效),application 測試會綠燈而正式環境出錯。

開發迴圈 `pytest -m "not integration"` 只跑 fake;CI 兩個實作都跑。
"""

from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import pytest

from app.domains.media.application.ports import MediaUnitOfWork
from app.domains.media.domain.entities import MediaItemStatus, MediaItemType
from tests.domains.media.builders import EVENT, ITEM, NOW, OTHER_USER, OWNER, an_item
from tests.domains.media.fakes import FakeMediaUnitOfWork


def same_item(actual, expected) -> bool:
    """比對時排除 updated_at:它由儲存層維護(見 MediaItemRepository.get 的承諾),
    SQLAlchemy 版本拿到的是資料庫寫入的時間,不會等於建構器給的值。"""
    return replace(actual, updated_at=None) == replace(expected, updated_at=None)


@pytest.fixture(params=["fake", pytest.param("sqlalchemy", marks=pytest.mark.integration)])
def uow_factory(request) -> Callable[[], MediaUnitOfWork]:
    if request.param == "fake":
        shared = FakeMediaUnitOfWork()  # 同一個實例 = 同一個「資料庫」
        return lambda: shared
    from app.domains.media.infrastructure.unit_of_work import SqlAlchemyMediaUnitOfWork

    session_factory = request.getfixturevalue("session_factory")
    return lambda: SqlAlchemyMediaUnitOfWork(session_factory)


async def test_getting_unknown_item_returns_none(uow_factory):
    async with uow_factory() as uow:
        assert await uow.media.get(ITEM, owner_id=OWNER) is None


async def test_added_item_can_be_read_back_after_commit(uow_factory):
    item = an_item()
    async with uow_factory() as uow:
        await uow.media.add(item)
        await uow.commit()

    async with uow_factory() as uow:
        assert same_item(await uow.media.get(item.id, owner_id=OWNER), item)


async def test_leaving_without_commit_rolls_back(uow_factory):
    item = an_item()
    async with uow_factory() as uow:
        await uow.media.add(item)
        # 故意不 commit

    async with uow_factory() as uow:
        assert await uow.media.get(item.id, owner_id=OWNER) is None


async def test_modifying_loaded_item_without_save_is_not_persisted(uow_factory):
    item = an_item(status=MediaItemStatus.PROCESSING)
    async with uow_factory() as uow:
        await uow.media.add(item)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.media.get(item.id, owner_id=OWNER)
        loaded.mark_failed(now=NOW)
        await uow.commit()  # 沒有 save

    async with uow_factory() as uow:
        reloaded = await uow.media.get(item.id, owner_id=OWNER)
        assert reloaded.status is MediaItemStatus.PROCESSING


async def test_saved_changes_are_persisted(uow_factory):
    item = an_item(status=MediaItemStatus.PROCESSING)
    async with uow_factory() as uow:
        await uow.media.add(item)
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.media.get(item.id, owner_id=OWNER)
        loaded.mark_ready(object_key="media/x.jpg", thumbnail_object_key=None, now=NOW)
        await uow.media.save(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        reloaded = await uow.media.get(item.id, owner_id=OWNER)
        assert reloaded.status is MediaItemStatus.READY
        assert reloaded.object_key == "media/x.jpg"


async def test_item_of_another_user_is_invisible(uow_factory):
    """審查 #6:不存在與無權限必須無法區分。"""
    item = an_item(owner_id=OTHER_USER)
    async with uow_factory() as uow:
        await uow.media.add(item)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.media.get(item.id, owner_id=OWNER) is None
        assert same_item(await uow.media.get_internal(item.id), item)  # worker 回呼看得到


async def test_find_active_clip_matches_same_range_only(uow_factory):
    """審查 #10:冪等判定以 captured_at + duration_sec 識別同一段範圍。"""
    clip = an_item(
        type=MediaItemType.CLIP,
        source_event_id=EVENT,
        duration_sec=15,
        status=MediaItemStatus.PROCESSING,
    )
    async with uow_factory() as uow:
        await uow.media.add(clip)
        await uow.commit()

    async with uow_factory() as uow:
        found = await uow.media.find_active_clip(
            owner_id=OWNER, source_event_id=EVENT, captured_at=clip.captured_at, duration_sec=15
        )
        assert same_item(found, clip)

        other_range = await uow.media.find_active_clip(
            owner_id=OWNER, source_event_id=EVENT, captured_at=clip.captured_at, duration_sec=20
        )
        assert other_range is None


async def test_find_active_clip_ignores_failed_attempts(uow_factory):
    """failed 的不算——使用者重送就是要重試。"""
    clip = an_item(
        type=MediaItemType.CLIP,
        source_event_id=EVENT,
        duration_sec=15,
        status=MediaItemStatus.FAILED,
    )
    async with uow_factory() as uow:
        await uow.media.add(clip)
        await uow.commit()

    async with uow_factory() as uow:
        assert (
            await uow.media.find_active_clip(
                owner_id=OWNER,
                source_event_id=EVENT,
                captured_at=clip.captured_at,
                duration_sec=15,
            )
            is None
        )


async def test_list_stale_processing_returns_only_old_processing_items(uow_factory):
    """審查 #9:逾時掃描不限擁有者,且不該掃到已完成的項目。"""
    stale = an_item(
        item_id=ITEM, status=MediaItemStatus.PROCESSING, updated_at=NOW - timedelta(hours=1)
    )
    fresh = an_item(item_id=OTHER_USER, status=MediaItemStatus.PROCESSING, updated_at=NOW)
    done = an_item(
        item_id=EVENT,
        status=MediaItemStatus.READY,
        object_key="media/x.jpg",
        updated_at=NOW - timedelta(hours=1),
    )
    async with uow_factory() as uow:
        for item in (stale, fresh, done):
            await uow.media.add(item)
        await uow.commit()

    async with uow_factory() as uow:
        found = await uow.media.list_stale_processing(changed_before=NOW - timedelta(minutes=15))
        assert [i.id for i in found] == [stale.id]


async def test_store_stamps_the_write_time(uow_factory):
    """逾時掃描(審查 #9)靠 updated_at,所以寫入後它一定要有值。"""
    item = an_item()
    async with uow_factory() as uow:
        await uow.media.add(item)
        await uow.commit()

    async with uow_factory() as uow:
        assert (await uow.media.get(item.id, owner_id=OWNER)).updated_at is not None
