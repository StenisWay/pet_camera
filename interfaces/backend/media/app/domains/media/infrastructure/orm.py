"""media_items 的 ORM 定義(01_資料模型與儲存規格.md 第 2.4 節)。

Media 是這張表的**擁有者**(13_ADR 第 1 節),所以這裡是欄位的權威定義;Album 服務
只定義自己讀寫的欄位視圖。

跨服務外鍵(user_id → users、device_id → devices、source_event_id → events)**不在
這裡宣告**:那三張表分別屬於 Auth、Device、Event 服務,不在本服務的 metadata 裡,
宣告了 create_all 也建不起來。實際的 FK 與 ON DELETE 行為由 db/ 的共用 migration
負責(資料模型第 2 節),這裡只保留欄位與索引。

型別與約束依 postgres-db-master:timestamptz、text + CHECK 表達值域、CHECK 具名。
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

STATUSES = ("processing", "ready", "failed")
TYPES = ("photo", "clip")
DRIVE_EXPORT_STATUSES = ("not_exported", "exporting", "exported", "failed")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class MediaItemRow(TimestampMixin, Base):
    __tablename__ = "media_items"
    __table_args__ = (
        CheckConstraint(_in_list("status", STATUSES), name="status_valid"),
        CheckConstraint(_in_list("type", TYPES), name="type_valid"),
        CheckConstraint(
            _in_list("drive_export_status", DRIVE_EXPORT_STATUSES),
            name="drive_export_status_valid",
        ),
        # 資料模型 §2.4:ready 時內容必填
        CheckConstraint(
            "status <> 'ready' OR object_key IS NOT NULL", name="ready_has_object_key"
        ),
        # duration_sec 只有 clip 有,且須 > 0
        CheckConstraint(
            "(type = 'clip' AND duration_sec > 0) OR (type = 'photo' AND duration_sec IS NULL)",
            name="duration_matches_type",
        ),
        Index("ix_media_items_owner_captured", "user_id", "captured_at", "id"),
        Index("ix_media_items_device_id", "device_id"),
        Index("ix_media_items_source_event_id", "source_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # UUIDv7,應用程式產生
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(nullable=True)
    captured_at: Mapped[datetime]

    # 這兩欄由 **Album 服務**寫入(資料模型 §2.4)。Media 擁有整張表的 schema,
    # 所以必須定義它們,但本服務的 mapper 絕不寫入——否則兩個服務會互相覆蓋。
    drive_export_status: Mapped[str] = mapped_column(Text, default="not_exported")
    drive_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
