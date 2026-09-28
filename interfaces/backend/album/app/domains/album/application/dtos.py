"""application 層的輸入(Command/Query)與輸出(Result)。

都是 frozen dataclass,不用 Pydantic——application 不依賴框架。
Pydantic 只在 presentation 層做 HTTP 驗證與序列化。
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.domains.album.domain.entities import AlbumItem


@dataclass(frozen=True)
class ListAlbumQuery:
    owner_id: uuid.UUID
    cursor: str | None = None
    limit: int | None = None
    date: str | None = None
    date_from: str | None = None
    date_to: str | None = None


@dataclass(frozen=True)
class AlbumItemResult:
    id: uuid.UUID
    type: str
    status: str
    captured_at: datetime
    duration_sec: int | None
    drive_export_status: str
    drive_file_id: str | None
    object_key: str | None
    thumbnail_object_key: str | None

    @classmethod
    def from_entity(cls, item: AlbumItem) -> "AlbumItemResult":
        return cls(
            id=item.id,
            type=item.type.value,
            status=item.status.value,
            captured_at=item.captured_at,
            duration_sec=item.duration_sec,
            drive_export_status=item.drive_export_status.value,
            drive_file_id=item.drive_file_id,
            object_key=item.object_key,
            thumbnail_object_key=item.thumbnail_object_key,
        )


@dataclass(frozen=True)
class AlbumPageResult:
    items: list[AlbumItemResult]
    next_cursor: str | None


@dataclass(frozen=True)
class ExportableItem:
    """交給 drive_export 上傳一個項目所需要的最小資訊。

    不回傳實體,避免其他領域繞過 use case 直接改狀態。檔名與 MIME 由 drive_export
    自己決定——那是 Drive 的事,不是相簿的事。
    """

    id: uuid.UUID
    object_key: str
    type: str
    captured_at: datetime


@dataclass(frozen=True)
class ExportPreparation:
    """一次匯出請求的受理結果(規格審查 #6)。"""

    accepted: list[ExportableItem]
    skipped_ids: list[uuid.UUID]  # 已在 exporting 中,跳過不重複送
