"""media_items 的 ORM 對應。

**這張表的 schema 由 Media 服務擁有**(13_ADR 第 1 節:Media 寫入,Album 讀取/管理),
Album 不對它發 migration。這裡的定義是為了查詢,以及更新 Album 負責的匯出欄位;
欄位需與 01_資料模型與儲存規格.md 第 2.4 節保持一致。

匯出逾時判定(規格審查 #7)用第 2.0 節既有的 updated_at,不新增欄位——處於 exporting
的項目不會再被 Media 服務寫入,updated_at 就是該次匯出的開始時間。
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

MEDIA_ITEM_STATUSES = ("processing", "ready", "failed")
DRIVE_EXPORT_STATUSES = ("not_exported", "exporting", "exported", "failed")


class MediaItemRow(TimestampMixin, Base):
    __tablename__ = "media_items"
    __table_args__ = (
        # 狀態欄位用 text + CHECK 表達值域,不用 PG enum(第 2.0 節)
        CheckConstraint(
            "status IN " + str(MEDIA_ITEM_STATUSES), name="status_valid"
        ),
        CheckConstraint(
            "drive_export_status IN " + str(DRIVE_EXPORT_STATUSES),
            name="drive_export_status_valid",
        ),
        CheckConstraint("type IN ('photo', 'clip')", name="type_valid"),
        # 與 db/models.py 的 ck_media_items_drive_file_id_presence 一致:
        # 只有 exported 才有 drive_file_id,其餘狀態必須是 null
        CheckConstraint(
            "(drive_export_status = 'exported') = (drive_file_id IS NOT NULL)",
            name="drive_file_id_presence",
        ),
        # 第 2.4 節:相簿分頁完全靠這個索引,id 一併納入是因為游標是 (captured_at, id)
        Index("ix_media_items_owner_captured", "user_id", "captured_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True)
    type: Mapped[str] = mapped_column(Text)
    # processing 期間尚未產生,status = 'ready' 時必填(第 2.4 節)
    object_key: Mapped[str | None] = mapped_column(Text)
    thumbnail_object_key: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column()
    drive_export_status: Mapped[str] = mapped_column(Text, default="not_exported")
    drive_file_id: Mapped[str | None] = mapped_column(Text)
