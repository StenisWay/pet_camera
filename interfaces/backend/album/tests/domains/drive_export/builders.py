import uuid
from datetime import UTC, datetime

from app.domains.drive_export.application.ports import ExportableMedia
from app.domains.drive_export.domain.entities import DriveConnection

OWNER = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
CAPTURED_AT = datetime(2026, 9, 20, 10, 30, 15, tzinfo=UTC)


def a_connection(
    *,
    owner_id: uuid.UUID = OWNER,
    refresh_token: str = "rt-1",
    folder_id: str | None = None,
) -> DriveConnection:
    return DriveConnection(
        id=uuid.uuid4(),
        owner_id=owner_id,
        refresh_token=refresh_token,
        connected_at=NOW,
        folder_id=folder_id,
    )


def exportable(
    *,
    item_id: uuid.UUID | None = None,
    object_key: str = "media/owner/2026/09/20/item.jpg",
    media_type: str = "photo",
) -> ExportableMedia:
    return ExportableMedia(
        id=item_id or uuid.uuid4(),
        object_key=object_key,
        media_type=media_type,
        captured_at=CAPTURED_AT,
    )
