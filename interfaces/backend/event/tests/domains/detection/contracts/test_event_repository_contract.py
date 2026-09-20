"""EventRepository 的行為承諾,每個實作都要通過。

合約內容直接來自 repositories.py 的 docstring。為什麼重要:application 測試全部建立在
fake 上,fake 的行為若與 SQLAlchemy 版不同(例如 get 回傳同一個物件、修改不用 save
就生效),application 測試會綠燈但上線出錯。

目前只跑 fake;正式實作寫好後把 "sqlalchemy" 加進 params,同一份測試自動套用。
"""

from collections.abc import Callable
from decimal import Decimal

import pytest

from app.domains.detection.application.ports import DetectionUnitOfWork
from app.domains.detection.domain.entities import Event, EventStatus, UploadedMedia
from tests.domains.detection.builders import DEVICE, EVENT, OTHER_DEVICE, at
from tests.domains.detection.fakes import FakeDetectionUnitOfWork

UowFactory = Callable[[], DetectionUnitOfWork]


@pytest.fixture(params=["fake"])
def uow_factory(request) -> UowFactory:
    if request.param == "fake":
        shared = FakeDetectionUnitOfWork()  # 同一個實例 = 同一個「資料庫」
        return lambda: shared
    raise AssertionError(f"未知的實作:{request.param}")


def an_event(*, id=EVENT, device_id=DEVICE) -> Event:
    return Event.begin(id=id, device_id=device_id, started_at=at(0))


def uploaded() -> UploadedMedia:
    return UploadedMedia(
        video_object_key="videos/x.mp4",
        thumbnail_object_key="thumbnails/x.jpg",
        confidence_score=Decimal("0.90"),
        duration_sec=12,
        ended_at=at(12),
    )


async def test_getting_an_unknown_event_returns_none(uow_factory: UowFactory):
    async with uow_factory() as uow:
        assert await uow.events.get(EVENT) is None


async def test_saved_event_is_readable_after_commit(uow_factory: UowFactory):
    event = an_event()

    async with uow_factory() as uow:
        await uow.events.save(event)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.events.get(EVENT) == event


async def test_leaving_without_commit_rolls_back(uow_factory: UowFactory):
    async with uow_factory() as uow:
        await uow.events.save(an_event())

    async with uow_factory() as uow:
        assert await uow.events.get(EVENT) is None


async def test_modifying_a_loaded_event_without_save_is_not_persisted(uow_factory: UowFactory):
    async with uow_factory() as uow:
        await uow.events.save(an_event())
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.events.get(EVENT)
        loaded.mark_failed()
        await uow.commit()  # 沒有 save

    async with uow_factory() as uow:
        assert (await uow.events.get(EVENT)).status is EventStatus.PROCESSING


async def test_saving_an_existing_event_updates_it(uow_factory: UowFactory):
    async with uow_factory() as uow:
        await uow.events.save(an_event())
        await uow.commit()

    async with uow_factory() as uow:
        loaded = await uow.events.get(EVENT)
        loaded.mark_ready(uploaded())
        await uow.events.save(loaded)
        await uow.commit()

    async with uow_factory() as uow:
        assert (await uow.events.get(EVENT)).status is EventStatus.READY


async def test_delete_all_by_device_returns_the_object_keys_to_clean_up(uow_factory: UowFactory):
    """01_資料模型 第 6 節:移除裝置時,R2 物件也要清掉。"""
    ready = an_event()
    ready.mark_ready(uploaded())

    async with uow_factory() as uow:
        await uow.events.save(ready)
        await uow.commit()

    async with uow_factory() as uow:
        purged = await uow.events.delete_all_by_device(DEVICE)
        await uow.commit()

    assert purged.deleted_count == 1
    assert sorted(purged.object_keys) == ["thumbnails/x.jpg", "videos/x.mp4"]

    async with uow_factory() as uow:
        assert await uow.events.get(EVENT) is None


async def test_delete_all_by_device_leaves_other_devices_alone(uow_factory: UowFactory):
    mine = an_event(device_id=DEVICE)
    theirs = an_event(id=OTHER_DEVICE, device_id=OTHER_DEVICE)

    async with uow_factory() as uow:
        await uow.events.save(mine)
        await uow.events.save(theirs)
        await uow.commit()

    async with uow_factory() as uow:
        await uow.events.delete_all_by_device(DEVICE)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.events.get(OTHER_DEVICE) is not None


async def test_delete_all_by_device_without_events_is_not_an_error(uow_factory: UowFactory):
    async with uow_factory() as uow:
        purged = await uow.events.delete_all_by_device(OTHER_DEVICE)

    assert purged.deleted_count == 0
    assert purged.object_keys == []
