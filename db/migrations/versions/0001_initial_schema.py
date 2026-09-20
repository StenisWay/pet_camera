"""initial schema:users / devices / events / media_items / refresh_tokens / push_tokens / oauth_identities

對應 rule_doc/功能需求/01_資料模型與儲存規格.md 第 2 節。

Revision ID: 0001
Revises:
Create Date: 2026-09-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 所有表共用:任何 UPDATE 都把 updated_at 推到當下,不依賴應用程式記得寫。
_SET_UPDATED_AT = """
create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;
"""

_TABLES_WITH_UPDATED_AT = (
    "users",
    "devices",
    "events",
    "media_items",
    "refresh_tokens",
    "push_tokens",
    "oauth_identities",
)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.execute(_SET_UPDATED_AT)

    # ---------------- users ----------------
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("char_length(email) between 3 and 320", name="ck_users_email_length"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    # ---------------- devices ----------------
    op.create_table(
        "devices",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("pairing_code", sa.Text(), nullable=True),
        sa.Column("pairing_code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_devices_user_id_users", ondelete="SET NULL"
        ),
        sa.CheckConstraint(
            "status in ('pending', 'paired', 'offline')", name="ck_devices_status"
        ),
        sa.CheckConstraint("char_length(name) between 1 and 64", name="ck_devices_name_length"),
        sa.CheckConstraint(
            "(status = 'pending') = (user_id is null)", name="ck_devices_pairing_state"
        ),
        sa.CheckConstraint(
            "(pairing_code is null) = (pairing_code_expires_at is null)",
            name="ck_devices_pairing_code_expiry",
        ),
    )
    op.create_index("ix_devices_user_id", "devices", ["user_id"])
    op.create_index(
        "uq_devices_pairing_code",
        "devices",
        ["pairing_code"],
        unique=True,
        postgresql_where=sa.text("pairing_code is not null"),
    )

    # ---------------- events ----------------
    op.create_table(
        "events",
        _uuid_pk(),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("video_object_key", sa.Text(), nullable=True),
        sa.Column("thumbnail_object_key", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_partial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"], name="fk_events_device_id_devices", ondelete="CASCADE"
        ),
        sa.CheckConstraint("event_type in ('motion')", name="ck_events_event_type"),
        sa.CheckConstraint(
            "status in ('processing', 'ready', 'failed')", name="ck_events_status"
        ),
        sa.CheckConstraint(
            "confidence_score >= 0 and confidence_score <= 1", name="ck_events_confidence_range"
        ),
        sa.CheckConstraint(
            "duration_sec is null or duration_sec > 0", name="ck_events_duration_positive"
        ),
        sa.CheckConstraint(
            "ended_at is null or ended_at >= started_at", name="ck_events_time_order"
        ),
        sa.CheckConstraint(
            "status <> 'ready' or (video_object_key is not null "
            "and thumbnail_object_key is not null and duration_sec is not null "
            "and ended_at is not null)",
            name="ck_events_ready_requires_media",
        ),
    )
    op.create_index(
        "ix_events_device_id_started_at",
        "events",
        ["device_id", sa.text("started_at desc")],
    )

    # ---------------- media_items ----------------
    op.create_table(
        "media_items",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=True),
        sa.Column("thumbnail_object_key", sa.Text(), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "drive_export_status",
            sa.Text(),
            server_default=sa.text("'not_exported'"),
            nullable=False,
        ),
        sa.Column("drive_file_id", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_media_items"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_media_items_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_media_items_device_id_devices",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_event_id"],
            ["events.id"],
            name="fk_media_items_source_event_id_events",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("type in ('photo', 'clip')", name="ck_media_items_type"),
        sa.CheckConstraint(
            "status in ('processing', 'ready', 'failed')", name="ck_media_items_status"
        ),
        sa.CheckConstraint(
            "drive_export_status in ('not_exported', 'exporting', 'exported', 'failed')",
            name="ck_media_items_drive_export_status",
        ),
        sa.CheckConstraint(
            "duration_sec is null or duration_sec > 0", name="ck_media_items_duration_positive"
        ),
        sa.CheckConstraint(
            "type <> 'photo' or (thumbnail_object_key is null and duration_sec is null)",
            name="ck_media_items_photo_has_no_clip_fields",
        ),
        sa.CheckConstraint(
            "status <> 'ready' or (object_key is not null and "
            "(type = 'photo' or (thumbnail_object_key is not null and duration_sec is not null)))",
            name="ck_media_items_ready_requires_media",
        ),
        sa.CheckConstraint(
            "(drive_export_status = 'exported') = (drive_file_id is not null)",
            name="ck_media_items_drive_file_id_presence",
        ),
    )
    op.create_index(
        "ix_media_items_user_id_captured_at",
        "media_items",
        ["user_id", sa.text("captured_at desc")],
    )
    op.create_index("ix_media_items_device_id", "media_items", ["device_id"])
    op.create_index("ix_media_items_source_event_id", "media_items", ["source_event_id"])

    # ---------------- refresh_tokens ----------------
    op.create_table(
        "refresh_tokens",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_refresh_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index(
        "ix_refresh_tokens_user_id_active",
        "refresh_tokens",
        ["user_id"],
        postgresql_where=sa.text("revoked_at is null"),
    )

    # ---------------- push_tokens ----------------
    op.create_table(
        "push_tokens",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.Text(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_push_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_push_tokens_user_id_users", ondelete="CASCADE"
        ),
        sa.CheckConstraint("platform in ('app', 'web')", name="ck_push_tokens_platform"),
    )
    op.create_index("ix_push_tokens_user_id", "push_tokens", ["user_id"])
    op.create_index(
        "uq_push_tokens_platform_token",
        "push_tokens",
        ["platform", sa.text("md5(token)")],
        unique=True,
    )

    # ---------------- oauth_identities ----------------
    op.create_table(
        "oauth_identities",
        _uuid_pk(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_identities"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_oauth_identities_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("provider in ('google', 'apple')", name="ck_oauth_identities_provider"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_identities_provider_provider_user_id"
        ),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_identities_user_id_provider"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])

    for table in _TABLES_WITH_UPDATED_AT:
        op.execute(
            f"create trigger trg_{table}_set_updated_at before update on {table} "
            f"for each row execute function set_updated_at()"
        )


def downgrade() -> None:
    for table in reversed(_TABLES_WITH_UPDATED_AT):
        op.execute(f"drop trigger if exists trg_{table}_set_updated_at on {table}")

    op.drop_table("oauth_identities")
    op.drop_table("push_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("media_items")
    op.drop_table("events")
    op.drop_table("devices")
    op.drop_table("users")
    op.execute("drop function if exists set_updated_at()")
