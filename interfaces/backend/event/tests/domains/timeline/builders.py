"""timeline 測試的固定資料。"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.domains.timeline.domain.entities import EventStatus, TimelineEvent

ALICE = uuid.UUID("00000000-0000-0000-0000-00000000a1ce")
BOB = uuid.UUID("00000000-0000-0000-0000-00000000b0b0")
DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
EVENT = uuid.UUID("00000000-0000-0000-0000-0000000000e1")

# 事件發生時間;「現在」一律用 NOW,相對於它推算保留期
STARTED = datetime(2026, 9, 20, 3, 0, 0, tzinfo=UTC)


def days(n: float) -> timedelta:
    return timedelta(days=n)


def a_timeline_event(
    *,
    id: uuid.UUID = EVENT,
    device_id: uuid.UUID = DEVICE,
    status: EventStatus = EventStatus.READY,
    started_at: datetime = STARTED,
    is_read: bool = False,
    is_partial: bool = False,
    with_media: bool | None = None,
) -> TimelineEvent:
    """預設是一筆正常可播放的事件;只寫出測試在乎的欄位。"""
    has_media = status is EventStatus.READY if with_media is None else with_media
    return TimelineEvent(
        id=id,
        device_id=device_id,
        status=status,
        confidence_score=Decimal("0.90"),
        started_at=started_at,
        duration_sec=12 if has_media else None,
        is_read=is_read,
        is_partial=is_partial,
        ended_at=started_at + timedelta(seconds=12) if has_media else None,
        video_object_key=f"videos/{device_id}/2026/09/20/{id}.mp4" if has_media else None,
        thumbnail_object_key=f"thumbnails/{device_id}/2026/09/20/{id}.jpg"
        if has_media
        else None,
    )
