"""events 的 ORM 對應。欄位需與 01_資料模型與儲存規格.md 第 2.3 節保持一致。

**為什麼放在 core 而不是某個領域的 infrastructure**:detection(F2 寫入)與
timeline(F3 讀取)兩個領域對應同一張表,這正是 13_ADR 第 1 節把 F2、F3 併成一個服務
的理由。ORM 的資料列定義是基礎設施細節,放進其中一個領域會讓另一個領域必須跨領域
import 它(違反分層規則第 4 條),所以定義在 core,兩個領域各自用自己的 mapper 轉成
自己的型別——detection 轉成 Event 聚合,timeline 轉成 TimelineEvent 唯讀視圖。

本服務擁有這張表,migration 由 db/ 統一產出(見該資料夾的 README)。
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

EVENT_STATUSES = ("processing", "ready", "failed")
EVENT_TYPES = ("motion",)


class EventRow(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        # 狀態欄位用 text + CHECK 表達值域,不用 PG enum(第 2.0 節)
        CheckConstraint("event_type in ('motion')", name="event_type"),
        CheckConstraint("status in ('processing', 'ready', 'failed')", name="status"),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 1", name="confidence_range"
        ),
        CheckConstraint("duration_sec is null or duration_sec > 0", name="duration_positive"),
        CheckConstraint("ended_at is null or ended_at >= started_at", name="time_order"),
        # 第 4 節狀態機:ready 代表影片與縮圖都已上傳完成
        CheckConstraint(
            "status <> 'ready' or (video_object_key is not null "
            "and thumbnail_object_key is not null and duration_sec is not null "
            "and ended_at is not null)",
            name="ready_requires_media",
        ),
        # 時間軸查詢:某裝置依時間倒序分頁(08_spec)
        Index("ix_events_device_id_started_at", "device_id", text("started_at desc")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    event_type: Mapped[str] = mapped_column(Text)
    # numeric(3,2) 對應 Decimal,不用 float:0.6 門檻的比較不能有浮點誤差
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(3, 2))
    status: Mapped[str] = mapped_column(Text)
    # processing 期間尚未上傳完成,故可為 null;ready 時由 CHECK 強制存在
    video_object_key: Mapped[str | None] = mapped_column(Text)
    thumbnail_object_key: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column()
    started_at: Mapped[datetime] = mapped_column()
    ended_at: Mapped[datetime | None] = mapped_column()
    is_read: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # 斷線導致的不完整片段(EVENT_003),見 07_spec 第 3 節
    is_partial: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
