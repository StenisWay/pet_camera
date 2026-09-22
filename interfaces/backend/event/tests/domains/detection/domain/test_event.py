"""Event 聚合:01_資料模型 第 4 節的狀態機 + 07_spec 第 3 節的後處理流程。"""

from decimal import Decimal

import pytest

from app.domains.detection.domain.entities import Event, EventStatus, UploadedMedia
from app.domains.detection.domain.exceptions import EventAlreadyFinalised
from app.domains.detection.domain.object_keys import thumbnail_key, video_key
from tests.domains.detection.builders import DEVICE, EVENT, at


def a_new_event() -> Event:
    return Event.begin(id=EVENT, device_id=DEVICE, started_at=at(0))


def uploaded(**overrides) -> UploadedMedia:
    defaults = dict(
        video_object_key=video_key(device_id=DEVICE, event_id=EVENT, started_at=at(0)),
        thumbnail_object_key=thumbnail_key(device_id=DEVICE, event_id=EVENT, started_at=at(0)),
        confidence_score=Decimal("0.90"),
        duration_sec=12,
        ended_at=at(12),
    )
    return UploadedMedia(**{**defaults, **overrides})


def test_new_event_is_processing_with_nothing_playable():
    """§3.1:錄影結束當下寫入 events,status = processing。"""
    event = a_new_event()

    assert event.status is EventStatus.PROCESSING
    assert event.video_object_key is None
    assert event.thumbnail_object_key is None
    assert event.duration_sec is None
    assert event.ended_at is None
    assert event.is_read is False
    assert event.is_partial is False
    assert event.is_finalised is False


def test_upload_success_makes_the_event_ready():
    """§3.4:上傳成功,status = ready,confidence_score 取事件期間最高值。"""
    event = a_new_event()

    event.mark_ready(uploaded(confidence_score=Decimal("0.95"), duration_sec=12))

    assert event.status is EventStatus.READY
    assert event.confidence_score == Decimal("0.95")
    assert event.duration_sec == 12
    assert event.ended_at == at(12)
    assert event.video_object_key is not None
    assert event.thumbnail_object_key is not None
    assert event.is_finalised is True


def test_upload_failure_marks_the_event_failed_with_no_playable_content():
    """§3.5:上傳失敗,status = failed,不建立可播放內容。"""
    event = a_new_event()

    event.mark_failed()

    assert event.status is EventStatus.FAILED
    assert event.video_object_key is None
    assert event.thumbnail_object_key is None
    assert event.is_finalised is True


def test_disconnected_recording_is_ready_but_partial():
    """§3 邊界案例:錄影中鏡頭斷線,已錄製部分仍可播放,但標記為不完整(EVENT_003)。

    不能用 failed 表達——failed 的語意是「沒有可播放內容」(規格審查 #9)。
    """
    event = a_new_event()

    event.mark_ready(uploaded(is_partial=True, duration_sec=7, ended_at=at(7)))

    assert event.status is EventStatus.READY
    assert event.is_partial is True
    assert event.duration_sec == 7  # 反映實際長度,不是原本預期的長度


@pytest.mark.parametrize(
    "finalise", [lambda e: e.mark_failed(), lambda e: e.mark_ready(uploaded())]
)
def test_a_finalised_event_cannot_be_finalised_again(finalise):
    """重試或重複投遞不該改寫已經定案的結果。"""
    event = a_new_event()
    event.mark_ready(uploaded(confidence_score=Decimal("0.70")))

    with pytest.raises(EventAlreadyFinalised):
        finalise(event)

    assert event.confidence_score == Decimal("0.70")  # 原本的結果沒被改掉


def test_object_keys_lists_what_has_to_be_deleted_from_r2():
    event = a_new_event()
    event.mark_ready(uploaded())

    assert event.object_keys() == [event.video_object_key, event.thumbnail_object_key]


def test_object_keys_of_an_event_without_upload_is_empty():
    """processing / failed 的事件沒有物件,刪除時不該送出空 key 給 R2。"""
    event = a_new_event()
    event.mark_failed()

    assert event.object_keys() == []


def test_r2_key_naming_rule():
    """01_資料模型與儲存規格.md 第 3.1 節,日期分層以事件開始時間(UTC)為準。"""
    assert (
        video_key(device_id=DEVICE, event_id=EVENT, started_at=at(0))
        == f"videos/{DEVICE}/2026/09/20/{EVENT}.mp4"
    )
    assert (
        thumbnail_key(device_id=DEVICE, event_id=EVENT, started_at=at(0))
        == f"thumbnails/{DEVICE}/2026/09/20/{EVENT}.jpg"
    )
