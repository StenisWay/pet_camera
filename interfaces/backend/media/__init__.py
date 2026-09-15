"""Media 服務——涵蓋 F5(剪輯與截圖)。擁有 media_items 表(負責寫入/建立)。

media_items 表同時被 Album 服務讀取/管理(見 album/__init__.py),是本專案唯一沒有
做到「一服務一資料表」的例外——理由見
rule_doc/功能需求/13_ADR_微服務與雙節點部署.md 第 1 節。Album 服務不匯入這裡的
MediaItem 型別,而是自行定義一份唯讀視圖,兩服務可各自獨立部署替換。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, Protocol
from uuid import UUID

from pydantic import BaseModel


class MediaItemType(str, Enum):
    PHOTO = "photo"
    CLIP = "clip"


class MediaItemStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaItem(BaseModel):
    id: UUID
    user_id: UUID
    device_id: UUID
    source_event_id: Optional[UUID] = None
    type: MediaItemType
    object_key: str
    thumbnail_object_key: Optional[str] = None
    duration_sec: Optional[int] = None
    status: MediaItemStatus
    captured_at: datetime
    created_at: datetime


class MediaItemRepository(Protocol):
    """本服務只負責建立與寫入生命週期,不負責列表查詢/刪除/匯出——那些是
    Album 服務的職責(見 album/__init__.py 的 AlbumRepository)。"""

    async def get_by_id(self, media_item_id: UUID) -> Optional[MediaItem]: ...

    async def create_processing(
        self,
        *,
        user_id: UUID,
        device_id: UUID,
        source_event_id: Optional[UUID],
        type: MediaItemType,
        captured_at: datetime,
    ) -> MediaItem: ...

    async def mark_ready(
        self,
        media_item_id: UUID,
        *,
        object_key: str,
        thumbnail_object_key: Optional[str],
        duration_sec: Optional[int],
    ) -> None: ...

    async def mark_failed(self, media_item_id: UUID) -> None: ...
