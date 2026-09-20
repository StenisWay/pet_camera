"""album:google_drive_credentials + media_items 游標分頁索引

對應 rule_doc/功能需求/12_spec_相簿與雲端匯出.md 第 2.1、2.3 節,
以及 01_資料模型與儲存規格.md 第 2.4、2.8 節(規格審查 #2)。

google_drive_credentials 由 Album 服務擁有,與 Auth 的 oauth_identities 分開:
那是「用 Google 登入」的身分綁定,這是「匯出到自己的 Drive」的 drive.file 授權,
scope、生命週期與撤銷時機都不同。

media_items 的索引改帶 id,是因為相簿分頁用的是 (captured_at, id) 組合游標:
同一秒保存的多個項目若只靠 captured_at 分頁,使用者往下捲時會重複或漏掉項目。

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_MEDIA_INDEX = "ix_media_items_user_id_captured_at"
NEW_MEDIA_INDEX = "ix_media_items_user_id_captured_at_id"


def upgrade() -> None:
    # ---------------- google_drive_credentials ----------------
    op.create_table(
        "google_drive_credentials",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("drive_folder_id", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_google_drive_credentials"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_google_drive_credentials_user_id_users",
            ondelete="CASCADE",
        ),
        # 一個使用者最多一份 Drive 授權
        sa.UniqueConstraint("user_id", name="uq_google_drive_credentials_user_id"),
    )
    # 0001 建立的 set_updated_at() 沿用,新表也要掛上
    op.execute(
        "create trigger trg_google_drive_credentials_set_updated_at "
        "before update on google_drive_credentials "
        "for each row execute function set_updated_at()"
    )

    # ---------------- media_items:游標分頁索引 ----------------
    # 先建新索引再刪舊的,中間不會有「相簿查詢沒有索引可用」的空窗。
    # concurrently 需要在交易外執行,本專案資料量小,直接建即可。
    op.create_index(
        NEW_MEDIA_INDEX,
        "media_items",
        ["user_id", sa.text("captured_at desc"), sa.text("id desc")],
    )
    op.drop_index(OLD_MEDIA_INDEX, table_name="media_items")


def downgrade() -> None:
    op.create_index(
        OLD_MEDIA_INDEX, "media_items", ["user_id", sa.text("captured_at desc")]
    )
    op.drop_index(NEW_MEDIA_INDEX, table_name="media_items")

    op.execute(
        "drop trigger if exists trg_google_drive_credentials_set_updated_at "
        "on google_drive_credentials"
    )
    op.drop_table("google_drive_credentials")
