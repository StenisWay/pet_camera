"""push_tokens 的 ORM 對應(01_資料模型與儲存規格.md 第 2.6 節)。

schema 的正本是 db/models.py 與共用的 db/migrations/;這裡的定義需與其一致,供本服務
存取與整合測試建表。刻意**不宣告**對 users.id 的外鍵:users 屬於 Auth 服務,不在本服務
的 metadata 裡;ON DELETE CASCADE 由共用 migration 建立(刪除帳號時一併帶走,
09_spec 第 3 節)。
"""

import uuid

from sqlalchemy import CheckConstraint, Index, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class PushTokenRow(TimestampMixin, Base):
    __tablename__ = "push_tokens"
    __table_args__ = (
        CheckConstraint("platform IN ('app', 'web')", name="platform"),
        # 同一個端點只登記一次,否則同一則通知會推兩遍。md5():Web Push subscription
        # 是 JSON 字串,直接建 B-tree 索引有長度上限風險
        Index("uq_push_tokens_platform_token", "platform", text("md5(token)"), unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    platform: Mapped[str] = mapped_column(Text)
    token: Mapped[str] = mapped_column(Text)
