"""Pet Camera 共用資料庫 model(SQLAlchemy 2.0)。

對應規格:rule_doc/功能需求/01_資料模型與儲存規格.md 第 2 節。
七個微服務共用同一個 PostgreSQL 資料庫(不做 database-per-service,
見 13_ADR_微服務與三節點部署.md 第 5 節),表的擁有權見該 ADR 第 1 節:

    Auth  -> users, refresh_tokens, oauth_identities, password_reset_tokens
    Device-> devices
    Event -> events
    Push  -> push_tokens
    Media -> media_items(寫入者);Album 唯讀/刪除同一張表
    Album -> google_drive_credentials

本檔是 Alembic autogenerate 的比對基準,不是服務的 ORM 層——各服務要不要用
ORM、用什麼型別對外,由服務自己決定(介面合約見 interfaces/backend/<service>/)。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# 約束命名規則:不設定的話 PostgreSQL 會產生隨機名稱,日後 migration 要 drop
# 約束時找不到名字。必須在任何 model 定義前掛到 MetaData 上。
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # 時間一律 timestamptz,以 UTC 儲存,顯示時才轉時區。
    # 不設定的話 Mapped[datetime] 會對應到沒有時區的 timestamp。
    type_annotation_map = {datetime: DateTime(timezone=True)}


def _pk() -> Mapped[uuid.UUID]:
    """uuid 主鍵。預設值由應用程式產生 UUIDv7(有時間排序、對 B-tree 友善);
    gen_random_uuid() 只是直接用 psql 插資料時的保險,不是預期路徑。"""
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), nullable=False)


def _updated_at() -> Mapped[datetime]:
    """由 trigger set_updated_at() 維護,不靠應用程式寫入。"""
    return mapped_column(server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(Text, nullable=False)
    # 僅用第三方登入建立、尚未設過密碼的帳號為 NULL(02_spec 第 2.7 節)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 連續帳密登入失敗次數與鎖定到期時間(02_spec 第 2.3 節)。放 Postgres 而非 Redis:
    # Redis 不做持久化,重啟就等於清空所有帳號的鎖定,那是可被主動觸發的暴力破解旁路。
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        CheckConstraint(
            "char_length(email) between 3 and 320", name="email_length"
        ),
        CheckConstraint("failed_login_attempts >= 0", name="failed_login_attempts_non_negative"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        # 唯一性用 email 本身即可,因為上面已強制小寫儲存
        UniqueConstraint("email", name="uq_users_email"),
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = _pk()
    # 未配對(pending)時為 NULL;解除配對會清空回 NULL(01 規格第 6 節)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_devices_user_id_users"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    pairing_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    pairing_code_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'paired', 'offline')", name="status"
        ),
        CheckConstraint("char_length(name) between 1 and 64", name="name_length"),
        # 03_spec:register 產生 pending + 配對碼且無 user_id;pair 綁定 user_id
        # 後轉 paired 並清除配對碼。offline 是已配對裝置失聯,仍有 user_id。
        CheckConstraint(
            "(status = 'pending') = (user_id is null)", name="pairing_state"
        ),
        # 配對碼與有效期一定同時存在或同時不存在
        CheckConstraint(
            "(pairing_code is null) = (pairing_code_expires_at is null)",
            name="pairing_code_expiry",
        ),
        Index("ix_devices_user_id", "user_id"),
        # 有效配對碼不可重複;已清除(NULL)的不納入
        Index(
            "uq_devices_pairing_code",
            "pairing_code",
            unique=True,
            postgresql_where=text("pairing_code is not null"),
        ),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = _pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="CASCADE", name="fk_events_device_id_devices"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # processing 期間影片尚未上傳完成,因此可為 NULL;ready 時由 CHECK 強制存在
    video_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # 錄影因鏡頭斷線提前結束:片段可播放但不完整(EVENT_003)。
    # 與 failed 不同——failed 是沒有可播放內容,見 07_spec 第 3 節。
    is_partial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        CheckConstraint("event_type in ('motion')", name="event_type"),
        CheckConstraint(
            "status in ('processing', 'ready', 'failed')", name="status"
        ),
        CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 1", name="confidence_range"
        ),
        CheckConstraint("duration_sec is null or duration_sec > 0", name="duration_positive"),
        CheckConstraint("ended_at is null or ended_at >= started_at", name="time_order"),
        # 01 規格第 4 節狀態機:ready 代表影片與縮圖都已上傳完成
        CheckConstraint(
            "status <> 'ready' or (video_object_key is not null "
            "and thumbnail_object_key is not null and duration_sec is not null "
            "and ended_at is not null)",
            name="ready_requires_media",
        ),
        # 時間軸查詢:某裝置依時間倒序分頁(08_spec)
        Index("ix_events_device_id_started_at", "device_id", text("started_at desc")),
    )


class MediaItem(Base):
    __tablename__ = "media_items"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_media_items_user_id_users"),
        nullable=False,
    )
    # 解除配對不刪相簿內容,裝置紀錄本身也不會被刪(只重置為 pending),
    # 因此用 RESTRICT:若哪天真的要刪 devices 列,必須先處理這裡的資料。
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="RESTRICT", name="fk_media_items_device_id_devices"),
        nullable=False,
    )
    # 來源事件會因解除配對被刪除,但相簿項目要留下 -> SET NULL
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("events.id", ondelete="SET NULL", name="fk_media_items_source_event_id_events"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(nullable=False)
    drive_export_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'not_exported'")
    )
    drive_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        CheckConstraint("type in ('photo', 'clip')", name="type"),
        CheckConstraint("status in ('processing', 'ready', 'failed')", name="status"),
        CheckConstraint(
            "drive_export_status in ('not_exported', 'exporting', 'exported', 'failed')",
            name="drive_export_status",
        ),
        CheckConstraint("duration_sec is null or duration_sec > 0", name="duration_positive"),
        # photo 沒有縮圖與長度,clip 兩者都要有(ready 之後)
        CheckConstraint(
            "type <> 'photo' or (thumbnail_object_key is null and duration_sec is null)",
            name="photo_has_no_clip_fields",
        ),
        CheckConstraint(
            "status <> 'ready' or (object_key is not null and "
            "(type = 'photo' or (thumbnail_object_key is not null and duration_sec is not null)))",
            name="ready_requires_media",
        ),
        CheckConstraint(
            "(drive_export_status = 'exported') = (drive_file_id is not null)",
            name="drive_file_id_presence",
        ),
        # 相簿依日期分組、倒序分頁(12_spec 第 2.1 節)。
        # id 一併納入是因為游標是 (captured_at, id) 組合:同一秒保存的多個項目
        # 若只靠 captured_at 分頁,使用者往下捲時會重複或漏掉項目。
        Index(
            "ix_media_items_user_id_captured_at_id",
            "user_id",
            text("captured_at desc"),
            text("id desc"),
        ),
        Index("ix_media_items_device_id", "device_id"),
        Index("ix_media_items_source_event_id", "source_event_id"),
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_tokens_user_id_users"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        Index("ix_refresh_tokens_user_id", "user_id"),
        # 驗證時只查「未撤銷」的那幾筆,rotation 軌跡不進這個索引
        Index(
            "ix_refresh_tokens_user_id_active",
            "user_id",
            postgresql_where=text("revoked_at is null"),
        ),
    )


class PasswordResetToken(Base):
    """忘記密碼的一次性重設 token(02_spec 第 2.4 節)。

    只存雜湊值;使用後標記 used_at 而不刪除,保留軌跡供異常排查。
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="CASCADE", name="fk_password_reset_tokens_user_id_users"
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

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


class PushToken(Base):
    __tablename__ = "push_tokens"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_push_tokens_user_id_users"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        CheckConstraint("platform in ('app', 'web')", name="platform"),
        # 同一個用戶端端點只該登記一次,否則同一則通知會推兩遍。
        # 用 hash 索引鍵避免 Web Push subscription JSON 過長撞到 B-tree 上限。
        Index(
            "uq_push_tokens_platform_token",
            "platform",
            text("md5(token)"),
            unique=True,
        ),
        Index("ix_push_tokens_user_id", "user_id"),
    )


class GoogleDriveCredential(Base):
    """相簿匯出用的 Google Drive 授權(12_spec_相簿與雲端匯出.md 第 2.3 節)。

    與 oauth_identities 是不同概念,不可混用:那是「用 Google/Apple 登入本系統」的
    身分綁定;這是「把相簿內容上傳到使用者自己的 Google Drive」的 drive.file 授權,
    scope、生命週期與撤銷時機都不同(使用者可以只解除 Drive 授權而繼續用 Google 登入)。
    """

    __tablename__ = "google_drive_credentials"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="CASCADE", name="fk_google_drive_credentials_user_id_users"
        ),
        nullable=False,
    )
    # TODO(安全): 目前明碼存放,加密方式(KMS / pgcrypto / 應用層)待確認
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    # 使用者 Drive 內「寵物攝影機」資料夾的 id,首次匯出時建立並寫回
    drive_folder_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        # 一個使用者最多一份 Drive 授權
        UniqueConstraint("user_id", name="uq_google_drive_credentials_user_id"),
    )


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_oauth_identities_user_id_users"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Apple 只在首次授權回傳 email,之後的登入可能沒有
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()

    __table_args__ = (
        CheckConstraint("provider in ('google', 'apple')", name="provider"),
        UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_identities_provider_provider_user_id"
        ),
        # 同一使用者在同一個 provider 只綁一個帳號
        UniqueConstraint("user_id", "provider", name="uq_oauth_identities_user_id_provider"),
        Index("ix_oauth_identities_user_id", "user_id"),
    )
