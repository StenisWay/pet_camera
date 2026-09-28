"""相簿項目實體:純 Python,業務規則的所在地。不知道資料庫、HTTP 或 Pydantic 的存在。

這是 media_items 的唯讀視圖——Media 服務負責建立與處理生命週期(processing → ready
/ failed),Album 只負責瀏覽、刪除,以及 Google Drive 匯出狀態這一段狀態機。
刻意不共用 Media 服務的型別,理由見 rule_doc/功能需求/13_ADR_微服務與三節點部署.md
第 1 節。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.domains.album.domain.exceptions import MediaItemNotReady


class MediaItemStatus(StrEnum):
    """01_資料模型與儲存規格.md 第 5 節的相簿項目狀態機(由 Media 服務推進)。"""

    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaItemType(StrEnum):
    PHOTO = "photo"
    CLIP = "clip"


class DriveExportStatus(StrEnum):
    """12_spec 第 2.3 節的匯出狀態機(由 Album 服務推進)。"""

    NOT_EXPORTED = "not_exported"
    EXPORTING = "exporting"
    EXPORTED = "exported"
    FAILED = "failed"


@dataclass
class AlbumItem:
    id: uuid.UUID
    owner_id: uuid.UUID
    device_id: uuid.UUID
    type: MediaItemType
    status: MediaItemStatus
    captured_at: datetime
    # processing 期間尚未產生檔案,object_key 為 None(資料模型第 2.4 節)
    object_key: str | None = None
    thumbnail_object_key: str | None = None
    duration_sec: int | None = None
    drive_export_status: DriveExportStatus = DriveExportStatus.NOT_EXPORTED
    drive_file_id: str | None = None
    export_state_changed_at: datetime | None = None

    # --- 查詢 ---

    def is_owned_by(self, user_id: uuid.UUID) -> bool:
        return self.owner_id == user_id

    @property
    def is_ready(self) -> bool:
        return self.status is MediaItemStatus.READY

    @property
    def object_keys(self) -> list[str]:
        """刪除項目時要一併清掉的 R2 物件(12_spec 第 2.2 節)。"""
        return [k for k in (self.object_key, self.thumbnail_object_key) if k]

    @property
    def is_exporting(self) -> bool:
        return self.drive_export_status is DriveExportStatus.EXPORTING

    def is_export_stale(self, *, now: datetime, after: timedelta) -> bool:
        """匯出卡住的判定(規格審查 #7)。

        匯出是背景工作,服務複本重啟後進行中的任務就消失了(ADR:VM-1/VM-2 是可被 LB
        隨時汰換的無狀態複本)。沒有這道收斂,項目會永遠停在「匯出中」。
        """
        if not self.is_exporting:
            return False
        if self.export_state_changed_at is None:
            return True
        return self.export_state_changed_at < now - after

    # --- 狀態轉移 ---

    def start_export(self, now: datetime) -> None:
        """12_spec 第 2.3 節:受理匯出,狀態先轉 exporting。

        只有 ready 的項目有檔案可上傳;已 exported 的仍可再次匯出(第 2.3.4 節)。
        重新匯出會在 Drive 建立新檔案,舊的 drive_file_id 當下就失效,必須清掉——
        留著它會違反「exported 才有 file id」這個不變條件。
        """
        if not self.is_ready:
            raise MediaItemNotReady()
        self.drive_export_status = DriveExportStatus.EXPORTING
        self.drive_file_id = None
        self.export_state_changed_at = now

    def complete_export(self, *, drive_file_id: str, now: datetime) -> None:
        self.drive_export_status = DriveExportStatus.EXPORTED
        self.drive_file_id = drive_file_id
        self.export_state_changed_at = now

    def fail_export(self, now: datetime) -> None:
        """DRIVE_002:匯出失敗不影響該項目在相簿內的正常瀏覽,只改匯出狀態。"""
        self.drive_export_status = DriveExportStatus.FAILED
        self.drive_file_id = None
        self.export_state_changed_at = now
