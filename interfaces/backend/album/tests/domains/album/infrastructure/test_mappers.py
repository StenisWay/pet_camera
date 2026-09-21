"""mapper 是隔離層,兩個方向都要驗:欄位有沒有對錯、有沒有漏。

用不連資料庫的 Row 物件即可——mapper 本身沒有查詢行為。
"""

import uuid
from datetime import UTC, datetime

from app.domains.album.domain.entities import DriveExportStatus, MediaItemStatus, MediaItemType
from app.domains.album.infrastructure.mappers import apply_to_row, to_entity
from app.domains.album.infrastructure.orm import MediaItemRow
from tests.domains.album.builders import an_item

CAPTURED_AT = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)
UPDATED_AT = datetime(2026, 9, 20, 11, 0, tzinfo=UTC)


def a_row(**overrides) -> MediaItemRow:
    row = MediaItemRow(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        device_id=uuid.uuid4(),
        type="clip",
        object_key="media/a.mp4",
        thumbnail_object_key="media-thumbnails/a.jpg",
        duration_sec=42,
        status="ready",
        captured_at=CAPTURED_AT,
        drive_export_status="exporting",
        drive_file_id=None,
    )
    row.updated_at = UPDATED_AT
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def test_row_maps_onto_the_entity():
    row = a_row()

    item = to_entity(row)

    assert item.id == row.id
    assert item.owner_id == row.user_id
    assert item.type is MediaItemType.CLIP
    assert item.status is MediaItemStatus.READY
    assert item.duration_sec == 42
    assert item.drive_export_status is DriveExportStatus.EXPORTING


def test_updated_at_becomes_the_export_state_timestamp():
    """匯出逾時判定用的是第 2.0 節既有的 updated_at,不另外加欄位。"""
    assert to_entity(a_row()).export_state_changed_at == UPDATED_AT


def test_only_export_fields_are_written_back():
    """其餘欄位屬於 Media 服務(13_ADR 第 1 節),Album 不碰。"""
    row = a_row(status="ready", object_key="media/original.mp4")
    item = an_item()
    item.start_export(CAPTURED_AT)
    item.complete_export(drive_file_id="drive-1", now=CAPTURED_AT)

    apply_to_row(item, row)

    assert row.drive_export_status == "exported"
    assert row.drive_file_id == "drive-1"
    assert row.status == "ready"
    assert row.object_key == "media/original.mp4"
