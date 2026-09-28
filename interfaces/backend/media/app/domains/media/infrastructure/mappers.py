"""Row ↔ Entity。

隔離層的代價,也是價值所在:資料表可以依 postgres-db-master 的規範自由演進
(例如 Album 之後在同一張表加欄位),不污染 domain 的業務模型。

apply_to_row 只同步本服務負責的欄位——drive_export_status / drive_file_id 屬 Album,
碰了就會在兩個服務之間互相覆蓋(13_ADR 第 1 節的共用表例外)。
"""

from app.domains.media.domain.entities import MediaItem, MediaItemStatus, MediaItemType
from app.domains.media.infrastructure.orm import MediaItemRow


def to_entity(row: MediaItemRow) -> MediaItem:
    return MediaItem(
        id=row.id,
        owner_id=row.user_id,
        device_id=row.device_id,
        source_event_id=row.source_event_id,
        type=MediaItemType(row.type),
        status=MediaItemStatus(row.status),
        captured_at=row.captured_at,
        object_key=row.object_key,
        thumbnail_object_key=row.thumbnail_object_key,
        duration_sec=row.duration_sec,
        updated_at=row.updated_at,
    )


def to_new_row(item: MediaItem) -> MediaItemRow:
    return MediaItemRow(
        id=item.id,
        user_id=item.owner_id,
        device_id=item.device_id,
        source_event_id=item.source_event_id,
        type=item.type.value,
        status=item.status.value,
        object_key=item.object_key,
        thumbnail_object_key=item.thumbnail_object_key,
        duration_sec=item.duration_sec,
        captured_at=item.captured_at,
    )


def apply_to_row(item: MediaItem, row: MediaItemRow) -> None:
    """只同步會變動的欄位:處理狀態與產出的檔案。"""
    row.status = item.status.value
    row.object_key = item.object_key
    row.thumbnail_object_key = item.thumbnail_object_key
    row.duration_sec = item.duration_sec
