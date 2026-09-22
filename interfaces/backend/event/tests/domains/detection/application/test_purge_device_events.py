"""PurgeDeviceEvents:01_資料模型 第 6 節、08_spec 第 3.3 節的串聯清除。"""

from decimal import Decimal

import pytest

from app.domains.detection.application.use_cases.purge_device_events import PurgeDeviceEvents
from app.domains.detection.domain.entities import Event, UploadedMedia
from tests.domains.detection.builders import DEVICE, EVENT, OTHER_DEVICE, at
from tests.domains.detection.fakes import FakeDetectionUnitOfWork, FakeMediaUploader


@pytest.fixture
def uow() -> FakeDetectionUnitOfWork:
    return FakeDetectionUnitOfWork()


@pytest.fixture
def uploader() -> FakeMediaUploader:
    return FakeMediaUploader()


@pytest.fixture
def use_case(uow, uploader) -> PurgeDeviceEvents:
    return PurgeDeviceEvents(uow=uow, uploader=uploader)


def a_ready_event(*, id=EVENT, device_id=DEVICE) -> Event:
    event = Event.begin(id=id, device_id=device_id, started_at=at(0))
    event.mark_ready(
        UploadedMedia(
            video_object_key=f"videos/{device_id}/2026/09/20/{id}.mp4",
            thumbnail_object_key=f"thumbnails/{device_id}/2026/09/20/{id}.jpg",
            confidence_score=Decimal("0.90"),
            duration_sec=12,
            ended_at=at(12),
        )
    )
    return event


async def test_removing_a_device_deletes_its_events(use_case, uow):
    uow.given(a_ready_event())

    result = await use_case.execute(DEVICE)

    assert result.deleted_count == 1
    assert await uow.events.get(EVENT) is None


async def test_the_r2_objects_are_deleted_too(use_case, uow, uploader):
    """規格審查 #8:R2 物件由本服務刪除,不是呼叫端——只有這裡組得出 key。"""
    event = uow.given(a_ready_event())

    await use_case.execute(DEVICE)

    assert sorted(uploader.deleted) == sorted(event.object_keys())


async def test_other_devices_are_untouched(use_case, uow):
    uow.given(a_ready_event())
    uow.given(a_ready_event(id=OTHER_DEVICE, device_id=OTHER_DEVICE))

    await use_case.execute(DEVICE)

    assert await uow.events.get(OTHER_DEVICE) is not None


async def test_a_device_without_events_is_not_an_error(use_case, uow, uploader):
    """已經清乾淨的裝置再刪一次要是冪等的——Device 服務可能會重試。"""
    result = await use_case.execute(DEVICE)

    assert result.deleted_count == 0
    assert uploader.deleted == []
    assert uow.commit_count == 1


async def test_events_without_uploaded_media_are_deleted_without_touching_r2(
    use_case, uow, uploader
):
    """processing / failed 的事件沒有物件,不該送空 key 給 R2。"""
    uow.given(Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0)))

    result = await use_case.execute(DEVICE)

    assert result.deleted_count == 1
    assert uploader.deleted == []


async def test_rows_are_committed_before_the_objects_are_deleted(uow):
    """順序是刻意的:先刪資料列並 commit,再刪 R2 物件。

    反過來的話,物件刪掉但資料列刪除失敗,時間軸會留下指向不存在物件的事件;
    現在這個順序最壞只是留下沒人指向的物件,等 lifecycle rule 到期自己消失。
    """
    uow.given(a_ready_event())
    committed_when_deleting: list[int] = []

    class SpyUploader(FakeMediaUploader):
        async def delete_many(self, keys):
            committed_when_deleting.append(uow.commit_count)
            await super().delete_many(keys)

    await PurgeDeviceEvents(uow=uow, uploader=SpyUploader()).execute(DEVICE)

    assert committed_when_deleting == [1]
