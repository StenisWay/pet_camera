"""sessions 的 SQLAlchemy model(refresh_tokens,01_資料模型 第 2.5 節)。"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class RefreshTokenRow(TimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        # 狀態值域用 text + CHECK(postgres-db-master 的規範:日後新增值只改 CHECK)
        CheckConstraint(
            "revoked_reason is null "
            "or revoked_reason in ('rotated', 'logged_out', 'superseded')",
            name="revoked_reason_valid",
        ),
        # 撤銷時間與理由要嘛都有、要嘛都沒有
        CheckConstraint(
            "(revoked_at is null) = (revoked_reason is null)",
            name="revoked_at_and_reason_together",
        ),
        Index("ix_refresh_tokens_user_id", "user_id"),
        # 驗證時只查未撤銷的紀錄;rotation 軌跡不進這個索引(01_資料模型 第 2.5 節)
        Index(
            "ix_refresh_tokens_user_id_active",
            "user_id",
            postgresql_where=text("revoked_at is null"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_tokens_user_id_users"),
    )
    # 只存雜湊,不存明碼
    token_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column()
    # rotation 時標記舊紀錄,不覆寫也不刪除(保留換發軌跡供異常排查)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # 為什麼被撤銷。§2.3.1 的重放偵測只對 'rotated' 生效——我們主動撤銷的
    # (登出、改密碼)不該把無辜的用戶端當成竊取者。
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
