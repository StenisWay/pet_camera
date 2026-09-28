"""即時畫面截圖的編排(11_spec 第 2.1 節、3 節)。

不碰資料庫、不碰 HTTP:UnitOfWork 與四個外部系統都是 fake。
"""

import pytest

from app.domains.media.application.ports import SourceDevice
from app.domains.media.application.use_cases.take_live_screenshot import TakeLiveScreenshot
from app.domains.media.domain.entities import MediaItemStatus, MediaItemType
from app.domains.media.domain.exceptions import (
    MediaItemNotFound,
    ScreenshotSourceUnavailable,
)
from tests.domains.media.builders import DEVICE, OTHER_USER, OWNER
from tests.domains.media.fakes import (
    FakeDeviceDirectory,
    FakeFrameSource,
    FakeMediaStorage,
    FakeMediaUnitOfWork,
    FixedClock,
    SequentialIds,
)


@pytest.fixture
def uow():
    return FakeMediaUnitOfWork()


@pytest.fixture
def clock():
    return FixedClock()


def build(uow, clock, *, device=None, frames=None, storage=None):
    devices = FakeDeviceDirectory({DEVICE: device} if device else {})
    return TakeLiveScreenshot(
        uow,
        devices,
        frames or FakeFrameSource(),
        storage or FakeMediaStorage(),
        clock,
        SequentialIds(),
    )


async def test_screenshot_of_online_device_is_ready_when_the_call_returns(uow, clock):
    """審查 #1:截圖同步完成,呼叫端拿到的就是 ready 的項目。"""
    use_case = build(uow, clock, device=SourceDevice(id=DEVICE, owner_id=OWNER, is_online=True))

    result = await use_case.execute(DEVICE, requester_id=OWNER)

    assert result.status is MediaItemStatus.READY
    assert result.type is MediaItemType.PHOTO
    assert result.captured_at == clock.now()
    assert result.source_event_id is None


async def test_screenshot_reserves_the_record_before_uploading(uow, clock):
    """R2 key 含 media_item_id,所以先寫 processing 取得 id,再上傳、再轉 ready。

    兩次 commit 不是浪費:順序倒過來(先傳檔再寫 DB)會在 DB 失敗時留下無法追蹤
    來源的孤兒檔案,正是 13_ADR 第 4 節要 Media 選 C 的理由。
    """
    storage = FakeMediaStorage()
    use_case = build(
        uow, clock, device=SourceDevice(id=DEVICE, owner_id=OWNER, is_online=True), storage=storage
    )

    result = await use_case.execute(DEVICE, requester_id=OWNER)

    assert uow.commit_count == 2
    assert result.object_key in storage.objects
    assert result.thumbnail_object_key in storage.objects  # 審查 #17


async def test_screenshot_of_unknown_device_is_reported_as_not_found(uow, clock):
    use_case = build(uow, clock, device=None)

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(DEVICE, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_screenshot_of_someone_elses_device_is_reported_as_not_found(uow, clock):
    """審查 #6:IDOR。非本人與不存在回同一個例外,不洩漏鏡頭是否存在。"""
    use_case = build(
        uow, clock, device=SourceDevice(id=DEVICE, owner_id=OTHER_USER, is_online=True)
    )

    with pytest.raises(MediaItemNotFound):
        await use_case.execute(DEVICE, requester_id=OWNER)

    assert uow.commit_count == 0


async def test_screenshot_of_offline_device_fails_without_creating_a_record(uow, clock):
    """鏡頭離線時沒有畫面可擷取(SCREENSHOT_001)。不留下任何相簿項目。"""
    use_case = build(uow, clock, device=SourceDevice(id=DEVICE, owner_id=OWNER, is_online=False))

    with pytest.raises(ScreenshotSourceUnavailable):
        await use_case.execute(DEVICE, requester_id=OWNER)

    assert uow.commit_count == 0
    assert uow.media.committed == {}


async def test_failed_capture_leaves_the_item_failed_not_dangling(uow, clock):
    """worker 擷幀失敗時,已建立的 processing 項目要收斂成 failed。

    否則它會一直留在相簿裡轉圈,直到 15 分鐘的逾時掃描才收掉(審查 #9)。
    """
    use_case = build(
        uow,
        clock,
        device=SourceDevice(id=DEVICE, owner_id=OWNER, is_online=True),
        frames=FakeFrameSource(available=False),
    )

    with pytest.raises(ScreenshotSourceUnavailable):
        await use_case.execute(DEVICE, requester_id=OWNER)

    [item] = uow.media.committed.values()
    assert item.status is MediaItemStatus.FAILED
    assert item.object_key is None


async def test_failed_upload_also_leaves_the_item_failed(uow, clock):
    """擷幀成功但 R2 掛了,一樣要收斂(不可留在 processing)。"""
    use_case = build(
        uow,
        clock,
        device=SourceDevice(id=DEVICE, owner_id=OWNER, is_online=True),
        storage=FakeMediaStorage(available=False),
    )

    with pytest.raises(ScreenshotSourceUnavailable):
        await use_case.execute(DEVICE, requester_id=OWNER)

    [item] = uow.media.committed.values()
    assert item.status is MediaItemStatus.FAILED
