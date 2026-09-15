"""Album 服務——涵蓋 F6(相簿與 Google Drive 匯出)。讀取/管理 media_items 表
(Media 服務負責寫入,見 media/__init__.py)。

AlbumItem 是本服務自行定義的唯讀視圖,刻意不匯入 media 服務的 MediaItem 型別——
兩服務對應到同一張表但不同的程式碼邊界,理由見
rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class DriveExportStatus(str, Enum):
    NOT_EXPORTED = "not_exported"
    EXPORTING = "exporting"
    EXPORTED = "exported"
    FAILED = "failed"


class AlbumItem(BaseModel):
    """media_items 表的唯讀視圖,僅含相簿瀏覽/匯出需要的欄位。"""

    id: UUID
    user_id: UUID
    device_id: UUID
    type: str  # "photo" / "clip",與 media 服務的 MediaItemType 同值域
    object_key: str
    thumbnail_object_key: Optional[str] = None
    duration_sec: Optional[int] = None
    status: str  # "processing" / "ready" / "failed"
    captured_at: datetime
    drive_export_status: DriveExportStatus
    drive_file_id: Optional[str] = None


@dataclass
class AlbumPage:
    items: list[AlbumItem]
    next_cursor: Optional[str]  # (captured_at, id) 組合游標,見 12_spec 第 2.1 節


class AlbumRepository(Protocol):
    async def list_by_user(
        self,
        user_id: UUID,
        *,
        cursor: Optional[str] = None,
        limit: int = 30,
        date: Optional[str] = None,
    ) -> AlbumPage: ...

    async def update_drive_export_status(
        self,
        media_item_id: UUID,
        *,
        status: DriveExportStatus,
        drive_file_id: Optional[str] = None,
    ) -> None: ...

    async def delete(self, media_item_id: UUID) -> None:
        """使用者於相簿手動刪除單一項目;呼叫端需另外刪除對應 R2 物件。"""
        ...

    async def delete_all_by_user(self, user_id: UUID) -> None:
        """由 Auth 服務跨服務呼叫(刪除帳號時串聯清除)。"""
        ...
