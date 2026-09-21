"""測試資料建構器。"""

import uuid
from datetime import UTC, datetime

from app.domains.notifications.domain.model import ReadyEvent

OWNER = uuid.UUID("00000000-0000-0000-0000-00000000a11c")
DEVICE_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d1")
EVENT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e1")
STARTED_AT = datetime(2026, 9, 20, 3, 14, tzinfo=UTC)
THUMBNAIL_KEY = f"thumbnails/{DEVICE_ID}/2026/09/20/{EVENT_ID}.jpg"


def a_ready_event(
    *,
    event_id: uuid.UUID = EVENT_ID,
    device_id: uuid.UUID = DEVICE_ID,
    confidence_score: float = 0.92,
    thumbnail_object_key: str | None = THUMBNAIL_KEY,
) -> ReadyEvent:
    return ReadyEvent(
        event_id=event_id,
        device_id=device_id,
        confidence_score=confidence_score,
        thumbnail_object_key=thumbnail_object_key,
        started_at=STARTED_AT,
    )
