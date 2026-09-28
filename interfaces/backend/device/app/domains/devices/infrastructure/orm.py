"""devices 資料表。

欄位依 01_資料模型與儲存規格.md 第 2.2 節,型別與約束規範依 postgres-db-master:
時間一律 timestamptz、狀態用 text + CHECK(不用 PG enum,日後新增狀態值只要改 CHECK)、
約束都有名字、外鍵欄位有索引。

**規格審查新增的欄位**(需寫回 01_資料模型 第 2.2 節):

| 欄位 | 理由 |
|---|---|
| hardware_id | 審查 #3:鏡頭重開機以此冪等,否則同一台實體鏡頭會累積多筆孤兒列 |
| device_secret_hash | 審查 #2:鏡頭端身分驗證,否則任何人都能偽造心跳 |

**status 值域縮小為 pending / paired**(審查 #6):offline 改由 last_seen_at 推導,
不落盤。理由見 domain/entities.py 的 DeviceStatus。
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

DEVICE_NAME_MAX_LENGTH = 30


class DeviceRow(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'paired')", name="status_valid"),
        # 01_資料模型 第 2.2 節:未配對時沒有擁有者,兩者必須同時成立
        CheckConstraint(
            "(status = 'pending') = (user_id IS NULL)", name="pending_iff_unowned"
        ),
        # 同節:pairing_code 與 pairing_code_expires_at 同時存在或同時為 null
        CheckConstraint(
            "(pairing_code IS NULL) = (pairing_code_expires_at IS NULL)",
            name="pairing_code_paired_with_expiry",
        ),
        # 已配對的裝置不該還留著配對碼(03_spec 第 2.2 節:配對完成即清除)
        CheckConstraint(
            "status = 'pending' OR pairing_code IS NULL", name="paired_has_no_code"
        ),
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {DEVICE_NAME_MAX_LENGTH}", name="name_length"
        ),
        Index("ix_devices_user_id", "user_id"),
        # 01_資料模型 第 2.2 節:有效期間內配對碼不可重複,用部分唯一索引強制
        Index(
            "uq_devices_pairing_code",
            "pairing_code",
            unique=True,
            postgresql_where=text("pairing_code IS NOT NULL"),
        ),
    )

    # 會出現在 API 路徑與 R2 object key 上,由應用程式產生 UUIDv7(第 2.0 節)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # 審查 #3:鏡頭自己持久化的識別碼
    hardware_id: Mapped[str] = mapped_column(Text, unique=True)
    # 外鍵 user_id -> users.id ON DELETE SET NULL 由 db/ 的共用 migration 建立,不在這裡
    # 宣告 ForeignKey:users 表屬於 Auth 服務(13_ADR 第 1 節),本服務的 metadata 裡
    # 沒有它,寫了會讓測試的 create_all 解不到目標表。
    # SET NULL 只是最後防線,正常路徑由 Auth 先呼叫
    # DELETE /internal/users/{user_id}/devices(審查 #8)。
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    name: Mapped[str] = mapped_column(Text)
    # 審查 #2:register 當時簽發,只存雜湊
    device_secret_hash: Mapped[str] = mapped_column(Text)
    pairing_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    pairing_code_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
