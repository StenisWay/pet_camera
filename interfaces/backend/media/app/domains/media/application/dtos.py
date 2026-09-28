"""application 的輸出 DTO。不用 Pydantic——application 不依賴框架。

不回傳實體給 presentation,避免外層繞過 use case 直接呼叫實體的狀態轉移方法。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domains.media.domain.entities import MediaItem, MediaItemStatus, MediaItemType


@dataclass(frozen=True)
class MediaItemResult:
    id: uuid.UUID
    type: MediaItemType
    status: MediaItemStatus
    captured_at: datetime
    source_event_id: uuid.UUID | None
    object_key: str | None
    thumbnail_object_key: str | None
    duration_sec: int | None
    # 僅 ready 的項目有連結(審查 #12;與 12_spec 第 2.1 節一致)
    content_url: str | None = None
    thumbnail_url: str | None = None

    @classmethod
    def from_entity(
        cls,
        item: MediaItem,
        *,
        content_url: str | None = None,
        thumbnail_url: str | None = None,
    ) -> "MediaItemResult":
        return cls(
            id=item.id,
            type=item.type,
            status=item.status,
            captured_at=item.captured_at,
            source_event_id=item.source_event_id,
            object_key=item.object_key,
            thumbnail_object_key=item.thumbnail_object_key,
            duration_sec=item.duration_sec,
            content_url=content_url,
            thumbnail_url=thumbnail_url,
        )
