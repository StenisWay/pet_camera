"""TimelineEvent:08_spec 第 2.2、2.3 節的播放、過期與已讀規則。"""

import pytest

from app.domains.timeline.domain.entities import EventStatus
from app.domains.timeline.domain.exceptions import (
    EventNotReady,
    EventProcessingFailed,
    VideoExpired,
)
from tests.domains.timeline.builders import STARTED, a_timeline_event, days


def test_ready_event_within_retention_is_playable():
    event = a_timeline_event(status=EventStatus.READY)

    event.ensure_playable(STARTED + days(1))  # 不丟例外


def test_processing_event_is_not_playable_yet():
    """§2.2 第 2 點:processing → TIMELINE_005(409)。"""
    event = a_timeline_event(status=EventStatus.PROCESSING)

    with pytest.raises(EventNotReady):
        event.ensure_playable(STARTED + days(1))


def test_failed_event_has_nothing_to_play():
    """§2.2 第 2 點:failed → EVENT_001(409),沿用 F2 的錯誤碼。"""
    event = a_timeline_event(status=EventStatus.FAILED)

    with pytest.raises(EventProcessingFailed):
        event.ensure_playable(STARTED + days(1))


@pytest.mark.parametrize(
    ("age", "expired"),
    [
        (days(6.9), False),
        (days(7), True),  # 保留期到期當下即視為過期
        (days(8), True),
    ],
)
def test_video_expires_seven_days_after_it_started(age, expired):
    """§2.2:保留期以 started_at + 7 天判定,與 R2 lifecycle rule 同一個基準。"""
    event = a_timeline_event()

    if expired:
        with pytest.raises(VideoExpired):
            event.ensure_playable(STARTED + age)
    else:
        event.ensure_playable(STARTED + age)


def test_status_is_checked_before_expiry():
    """還在處理中的舊事件應該說「還沒好」,而不是「已過期」——兩者的復原路徑不同。"""
    event = a_timeline_event(status=EventStatus.PROCESSING)

    with pytest.raises(EventNotReady):
        event.ensure_playable(STARTED + days(30))


def test_ready_event_without_a_video_key_is_not_playable():
    """資料表的 CHECK 擋得住這種列,但讀取端不該因為髒資料就丟 500。"""
    event = a_timeline_event(status=EventStatus.READY, with_media=False)

    with pytest.raises(EventNotReady):
        event.ensure_playable(STARTED + days(1))


@pytest.mark.parametrize(
    ("age", "available"),
    [
        (days(7), True),  # 影片過期後縮圖仍在(§4)
        (days(29.9), True),
        (days(30), False),
        (days(31), False),
    ],
)
def test_thumbnail_is_kept_for_thirty_days(age, available):
    """§4:影片過期後縮圖仍可顯示,30 天後才變成佔位圖示(TIMELINE_004)。"""
    event = a_timeline_event()

    assert event.thumbnail_available(STARTED + age) is available


def test_processing_event_has_no_thumbnail_yet():
    event = a_timeline_event(status=EventStatus.PROCESSING)

    assert event.thumbnail_available(STARTED) is False


@pytest.mark.parametrize("target", [True, False])
def test_read_flag_can_be_set_both_ways(target):
    """§2.3:播放後標記已讀;誤點後也能改回未讀(規格審查 #10)。"""
    event = a_timeline_event(is_read=not target)

    event.mark_read(target)

    assert event.is_read is target
