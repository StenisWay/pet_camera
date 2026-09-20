"""Row ↔ Entity。

隔離層的代價,也是價值所在:資料表可以依 postgres-db-master 的規範演進
(加 source_event_id、外鍵、CHECK),業務模型不受影響。
"""

from app.domains.album.domain.entities import (
    AlbumItem,
    DriveExportStatus,
    MediaItemStatus,
    MediaItemType,
)
from app.domains.album.infrastructure.orm import MediaItemRow


def to_entity(row: MediaItemRow) -> AlbumItem:
    return AlbumItem(
        id=row.id,
        owner_id=row.user_id,
        device_id=row.device_id,
        type=MediaItemType(row.type),
        status=MediaItemStatus(row.status),
        captured_at=row.captured_at,
        object_key=row.object_key,
        thumbnail_object_key=row.thumbnail_object_key,
        duration_sec=row.duration_sec,
        drive_export_status=DriveExportStatus(row.drive_export_status),
        drive_file_id=row.drive_file_id,
        # 見 orm.py:匯出狀態的變更時間就是這一列的 updated_at
        export_state_changed_at=row.updated_at,
    )


def apply_to_row(item: AlbumItem, row: MediaItemRow) -> None:
    """只同步 Album 服務負責的欄位。

    其餘欄位屬於 Media 服務(13_ADR 第 1 節),Album 不碰;updated_at 由資料庫的
    onupdate/trigger 維護,也不在這裡寫。
    """
    row.drive_export_status = item.drive_export_status.value
    row.drive_file_id = item.drive_file_id
