"""EventRow ↔ TimelineEvent。

mapper 是隔離層的代價,也是價值所在:資料表可以依 postgres-db-master 的規範演進
(加欄位、改索引),業務型別不受影響。timeline 只映射讀取需要的欄位。
"""

from decimal import Decimal

from app.core.orm import EventRow
from app.domains.timeline.domain.entities import EventStatus, TimelineEvent


def to_timeline_event(row: EventRow) -> TimelineEvent:
    return TimelineEvent(
        id=row.id,
        device_id=row.device_id,
        status=EventStatus(row.status),
        # numeric(3,2) 經 asyncpg 回來已經是 Decimal,但直接用 psql 塞的資料可能是別的型別
        confidence_score=Decimal(str(row.confidence_score)),
        started_at=row.started_at,
        duration_sec=row.duration_sec,
        is_read=row.is_read,
        is_partial=row.is_partial,
        ended_at=row.ended_at,
        video_object_key=row.video_object_key,
        thumbnail_object_key=row.thumbnail_object_key,
    )
