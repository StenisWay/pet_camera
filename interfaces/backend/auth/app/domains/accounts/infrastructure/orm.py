"""accounts 的 SQLAlchemy model。

schema 的權威定義在 db/models.py 與 db/migrations/(見 01_資料模型與儲存規格.md
第 2.1、2.9 節);這裡的 model 只是本服務讀寫自己那幾張表的映射,欄位、型別與
約束必須與那邊一致,但**不是** domain 實體——實體是純 Python,由 mappers.py 轉換。

型別與約束依 postgres-db-master 的規範:時間 timestamptz、狀態用 text + CHECK、
外鍵都有索引、約束都有名字。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class UserRow(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("char_length(email) between 3 and 320", name="email_length"),
        # 大小寫正規化由應用程式負責,這條約束是最後一道防線:漏正規化時直接失敗,
        # 而不是安靜地產生 A@x.com 與 a@x.com 兩個帳號(02_spec 第 2.1 節)
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "failed_login_attempts >= 0", name="failed_login_attempts_non_negative"
        ),
        UniqueConstraint("email", name="uq_users_email"),
    )

    # 會出現在 API 路徑上,由應用程式產生 UUIDv7(01_資料模型 第 2.0 節)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    email: Mapped[str] = mapped_column(Text)
    # 僅第三方登入建立、尚未設過密碼的帳號為 NULL(02_spec 第 2.7 節)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)


class PasswordResetTokenRow(TimestampMixin, Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
        Index("ix_password_reset_tokens_user_id", "user_id"),
        # 驗證時只看還沒用過的那幾筆
        Index(
            "ix_password_reset_tokens_user_id_unused",
            "user_id",
            postgresql_where=text("used_at is null"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "users.id", ondelete="CASCADE", name="fk_password_reset_tokens_user_id_users"
        ),
    )
    token_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column()
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
