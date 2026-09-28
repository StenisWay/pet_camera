"""測試資料建構器:讓測試只寫出「跟這個情境有關」的欄位。"""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.domains.album.domain.entities import (
    AlbumItem,
    DriveExportStatus,
    MediaItemStatus,
    MediaItemType,
)

OWNER = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
# 相簿依日期分組用台北時間(12_spec 第 2.1 節),資料仍以 UTC 儲存
TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)


def taipei(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """以台北當地時間表達一個拍攝時刻,讀測試時不必自己換算時差。"""
    return datetime(year, month, day, hour, minute, tzinfo=TAIPEI)


def an_item(
    *,
    item_id: uuid.UUID | None = None,
    owner_id: uuid.UUID = OWNER,
    type: MediaItemType = MediaItemType.PHOTO,
    status: MediaItemStatus = MediaItemStatus.READY,
    captured_at: datetime = CAPTURED_AT,
    object_key: str | None = "media/owner/2026/09/20/item.jpg",
    thumbnail_object_key: str | None = None,
    drive_export_status: DriveExportStatus = DriveExportStatus.NOT_EXPORTED,
    drive_file_id: str | None = None,
    export_state_changed_at: datetime | None = None,
) -> AlbumItem:
    return AlbumItem(
        id=item_id or uuid.uuid4(),
        owner_id=owner_id,
        device_id=uuid.uuid4(),
        type=type,
        status=status,
        captured_at=captured_at,
        object_key=None if status is MediaItemStatus.PROCESSING else object_key,
        thumbnail_object_key=thumbnail_object_key,
        drive_export_status=drive_export_status,
        drive_file_id=drive_file_id,
        export_state_changed_at=export_state_changed_at,
    )
