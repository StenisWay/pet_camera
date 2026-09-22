"""EventRow ↔ Event 聚合。"""

from decimal import Decimal

from app.core.orm import EventRow
from app.domains.detection.domain.entities import Event, EventStatus, EventType


def to_entity(row: EventRow) -> Event:
    return Event(
        id=row.id,
        device_id=row.device_id,
        started_at=row.started_at,
        event_type=EventType(row.event_type),
        status=EventStatus(row.status),
        confidence_score=Decimal(str(row.confidence_score)),
        video_object_key=row.video_object_key,
        thumbnail_object_key=row.thumbnail_object_key,
        duration_sec=row.duration_sec,
        ended_at=row.ended_at,
        is_read=row.is_read,
        is_partial=row.is_partial,
    )


def to_new_row(event: Event) -> EventRow:
    return EventRow(
        id=event.id,
        device_id=event.device_id,
        event_type=event.event_type.value,
        confidence_score=event.confidence_score,
        status=event.status.value,
        video_object_key=event.video_object_key,
        thumbnail_object_key=event.thumbnail_object_key,
        duration_sec=event.duration_sec,
        started_at=event.started_at,
        ended_at=event.ended_at,
        is_read=event.is_read,
        is_partial=event.is_partial,
    )


def apply_to_row(event: Event, row: EventRow) -> None:
    """只同步會變動的欄位。

    id、device_id、started_at、event_type 在事件建立後就不再改變,寫回去只是
    讓「誰能改什麼」變得模糊;is_read 屬於 timeline,detection 不碰。
    """
    row.status = event.status.value
    row.confidence_score = event.confidence_score
    row.video_object_key = event.video_object_key
    row.thumbnail_object_key = event.thumbnail_object_key
    row.duration_sec = event.duration_sec
    row.ended_at = event.ended_at
    row.is_partial = event.is_partial
