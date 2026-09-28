"""測試資料建構器:讓測試只寫出「跟這個情境有關」的欄位。"""

import uuid
from datetime import UTC, datetime

from app.domains.media.domain.entities import (
    MediaItem,
    MediaItemStatus,
    MediaItemType,
    SourceEvent,
)

OWNER = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
OTHER_USER = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
DEVICE = uuid.UUID("00000000-0000-0000-0000-0000000000c3")
EVENT = uuid.UUID("00000000-0000-0000-0000-0000000000d4")
ITEM = uuid.UUID("00000000-0000-0000-0000-0000000000e5")

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
EVENT_STARTED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def an_event(
    *,
    event_id: uuid.UUID = EVENT,
    owner_id: uuid.UUID = OWNER,
    device_id: uuid.UUID = DEVICE,
    status: str = "ready",
    started_at: datetime = EVENT_STARTED_AT,
    duration_sec: int = 45,
) -> SourceEvent:
    return SourceEvent(
        id=event_id,
        owner_id=owner_id,
        device_id=device_id,
        status=status,
        started_at=started_at,
        duration_sec=duration_sec,
    )


def an_item(
    *,
    item_id: uuid.UUID = ITEM,
    owner_id: uuid.UUID = OWNER,
    device_id: uuid.UUID = DEVICE,
    source_event_id: uuid.UUID | None = None,
    type: MediaItemType = MediaItemType.PHOTO,
    status: MediaItemStatus = MediaItemStatus.PROCESSING,
    captured_at: datetime = NOW,
    object_key: str | None = None,
    thumbnail_object_key: str | None = None,
    duration_sec: int | None = None,
    updated_at: datetime | None = NOW,
) -> MediaItem:
    return MediaItem(
        id=item_id,
        owner_id=owner_id,
        device_id=device_id,
        source_event_id=source_event_id,
        type=type,
        status=status,
        captured_at=captured_at,
        object_key=object_key,
        thumbnail_object_key=thumbnail_object_key,
        duration_sec=duration_sec,
        updated_at=updated_at,
    )
