"""application 的輸入輸出 DTO。不用 Pydantic——application 不依賴框架。"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.domains.timeline.domain.entities import EventStatus


@dataclass(frozen=True)
class ListTimelineQuery:
    """對應 GET /devices/{device_id}/events 的查詢字串,欄位都還是「使用者送來的原樣」。

    轉成值物件(PageSize / DateRange / TimelineCursor)是 use case 的第一件事,
    驗證失敗一律是 VAL_001。
    """

    device_id: UUID
    requester_id: UUID
    cursor: str | None = None
    limit: int | None = None
    date: str | None = None
    tz: str | None = None
    started_from: int | None = None
    started_to: int | None = None


@dataclass(frozen=True)
class TimelineItemResult:
    id: UUID
    device_id: UUID
    status: EventStatus
    confidence_score: Decimal
    started_at: datetime
    ended_at: datetime | None
    duration_sec: int | None
    is_read: bool
    is_partial: bool
    thumbnail_url: str | None


@dataclass(frozen=True)
class TimelinePageResult:
    items: list[TimelineItemResult]
    next_cursor: str | None
