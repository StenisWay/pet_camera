"""相簿項目的建立與處理狀態機(資料模型第 5 節、11_spec 第 2 節)。"""

import uuid
from datetime import timedelta

import pytest

from app.domains.media.domain.entities import (
    ClipRange,
    MediaItem,
    MediaItemStatus,
    MediaItemType,
)
from app.domains.media.domain.exceptions import MediaItemNotProcessing
from tests.domains.media.builders import (
    DEVICE,
    EVENT_STARTED_AT,
    ITEM,
    NOW,
    OTHER_USER,
    OWNER,
    an_event,
    an_item,
)

STALE_AFTER = timedelta(minutes=15)


def test_new_photo_starts_as_processing_without_any_file():
    """審查 #1:截圖同步回應,但仍先寫 processing——R2 key 含 media_item_id,
    必須先有 id 才算得出 key,順序倒過來會產生孤兒檔案(13_ADR 第 4 節選 C)。"""
    item = MediaItem.start_photo(
        item_id=ITEM, owner_id=OWNER, device_id=DEVICE, captured_at=NOW, now=NOW
    )

    assert item.status is MediaItemStatus.PROCESSING
    assert item.type is MediaItemType.PHOTO
    assert item.object_key is None
    assert item.source_event_id is None


def test_event_screenshot_records_its_source_event():
    """資料模型 §2.4:來自既有事件時填入 source_event_id。"""
    event = an_event()

    item = MediaItem.start_photo(
        item_id=ITEM,
        owner_id=OWNER,
        device_id=event.device_id,
        captured_at=event.started_at + timedelta(seconds=10),
        source_event_id=event.id,
        now=NOW,
    )

    assert item.source_event_id == event.id


def test_clip_captured_at_follows_the_source_event_not_the_button_press():
    """審查 #11:相簿依 captured_at 分組(F6 §2.1)。

    填按鈕按下的時間,三天前事件剪出來的片段會被分到「今天」,使用者找不到。
    """
    event = an_event(started_at=EVENT_STARTED_AT, duration_sec=45)
    clip_range = ClipRange(start_sec=30, end_sec=45)

    item = MediaItem.start_clip(
        item_id=ITEM, owner_id=OWNER, event=event, clip_range=clip_range, now=NOW
    )

    assert item.captured_at == EVENT_STARTED_AT + timedelta(seconds=30)
    assert item.duration_sec == 15
    assert item.type is MediaItemType.CLIP
    assert item.device_id == event.device_id


def test_item_is_owned_by_its_owner_only():
    """IDOR 的第一道防線:擁有權判斷是業務規則,不是查詢條件(審查 #6)。"""
    item = an_item(owner_id=OWNER)

    assert item.is_owned_by(OWNER)
    assert not item.is_owned_by(OTHER_USER)


def test_marking_ready_publishes_the_files():
    item = an_item(type=MediaItemType.CLIP, duration_sec=15)

    item.mark_ready(
        object_key="media/a/2026/09/20/x.mp4",
        thumbnail_object_key="media-thumbnails/a/2026/09/20/x.jpg",
        now=NOW,
    )

    assert item.status is MediaItemStatus.READY
    assert item.object_key == "media/a/2026/09/20/x.mp4"
    assert item.updated_at == NOW


def test_marking_failed_leaves_no_playable_content():
    """CLIP_002 / SCREENSHOT_001:失敗不建立可用內容(11_spec 第 5 節)。"""
    item = an_item()

    item.mark_failed(now=NOW)

    assert item.status is MediaItemStatus.FAILED
    assert item.object_key is None


@pytest.mark.parametrize("status", [MediaItemStatus.READY, MediaItemStatus.FAILED])
def test_finished_item_cannot_be_advanced_again(status):
    """狀態機只允許 processing → ready / failed(資料模型第 5 節)。

    worker 重試造成的重複回呼不該把 failed 翻回 ready。
    """
    item = an_item(status=status)

    with pytest.raises(MediaItemNotProcessing):
        item.mark_ready(object_key="media/x.jpg", thumbnail_object_key=None, now=NOW)
    with pytest.raises(MediaItemNotProcessing):
        item.mark_failed(now=NOW)


def test_photo_never_carries_a_duration():
    """資料模型 §2.4:duration_sec 只有 clip 才有。"""
    item = MediaItem.start_photo(
        item_id=ITEM, owner_id=OWNER, device_id=DEVICE, captured_at=NOW, now=NOW
    )

    assert item.duration_sec is None


def test_object_keys_include_thumbnail_when_present():
    item = an_item(
        status=MediaItemStatus.READY,
        object_key="media/a.mp4",
        thumbnail_object_key="media-thumbnails/a.jpg",
    )

    assert item.object_keys == ["media/a.mp4", "media-thumbnails/a.jpg"]


def test_processing_item_has_no_object_yet():
    assert an_item(status=MediaItemStatus.PROCESSING).object_keys == []


def test_processing_longer_than_limit_is_considered_stuck():
    """審查 #9:背景工作在無狀態複本上跑,複本被汰換後任務就消失了。

    沒有這道收斂,相簿卡片會永遠轉圈(與 F6 的 exporting 15 分鐘規則對稱)。
    """
    item = an_item(
        status=MediaItemStatus.PROCESSING, updated_at=NOW - STALE_AFTER - timedelta(seconds=1)
    )

    assert item.is_stale_processing(now=NOW, after=STALE_AFTER)


def test_recently_started_processing_is_not_stuck():
    item = an_item(status=MediaItemStatus.PROCESSING, updated_at=NOW)

    assert not item.is_stale_processing(now=NOW, after=STALE_AFTER)


def test_finished_item_is_never_stuck():
    item = an_item(status=MediaItemStatus.READY, updated_at=NOW - timedelta(days=30))

    assert not item.is_stale_processing(now=NOW, after=STALE_AFTER)


def test_new_items_get_distinct_identity():
    """id 由應用程式產生(UUIDv7),不靠資料庫預設值——R2 key 要先算得出來。"""
    first = MediaItem.start_photo(
        item_id=uuid.UUID(int=1), owner_id=OWNER, device_id=DEVICE, captured_at=NOW, now=NOW
    )
    second = MediaItem.start_photo(
        item_id=uuid.UUID(int=2), owner_id=OWNER, device_id=DEVICE, captured_at=NOW, now=NOW
    )

    assert first.id != second.id


def test_item_without_a_write_time_is_treated_as_stuck():
    """updated_at 由資料庫維護,理論上不會是 None。

    真的遇到(例如手動塞進去的測試資料)就當成卡住——寧可誤判一筆去重跑,
    也不要讓它永遠留在相簿裡轉圈。
    """
    item = an_item(status=MediaItemStatus.PROCESSING, updated_at=None)

    assert item.is_stale_processing(now=NOW, after=STALE_AFTER)
