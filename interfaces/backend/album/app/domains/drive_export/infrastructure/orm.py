"""google_drive_credentials 的 ORM 對應。

這張表是規格審查 #2 的產物:12_spec 第 2.3 節要求保存 Google 授權,但
01_資料模型與儲存規格.md 原本沒有對應的表。它由 Album 服務擁有(唯一一張)。
"""

import uuid
from datetime import datetime

from sqlalchemy import Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class DriveCredentialRow(TimestampMixin, Base):
    __tablename__ = "google_drive_credentials"

    # 01_資料模型與儲存規格.md 第 2.0 節:每張表都有 id/created_at/updated_at
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 一個使用者最多一份 Drive 授權,以唯一索引保證
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True, index=True)
    refresh_token: Mapped[str] = mapped_column(Text)
    drive_folder_id: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime] = mapped_column()
