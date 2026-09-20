"""auth:登入失敗鎖定欄位 + password_reset_tokens

對應 rule_doc/功能需求/02_spec_登入註冊與密碼重設.md 第 2.3、2.4 節,
以及 01_資料模型與儲存規格.md 第 2.1、2.9 節(規格審查 #2、#3)。

兩者都刻意放 Postgres 而不是共用 Redis:Redis 不做持久化(01 規格第 7.2 節),
重啟會清空所有鎖定、並讓已寄出的重設連結全部失效。

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-20

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- users:登入失敗鎖定 ----------------
    # 既有列補 0 之後才拿掉 server_default 以外的顧慮;這裡直接帶 default,
    # 表目前資料量小(單一使用者規模),不需要 expand-contract 分批回填。
    op.add_column(
        "users",
        sa.Column(
            "failed_login_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_users_failed_login_attempts_non_negative",
        "users",
        "failed_login_attempts >= 0",
    )

    # ---------------- password_reset_tokens ----------------
    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name="pk_password_reset_tokens"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_password_reset_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("token_hash", name="uq_password_reset_tokens_token_hash"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index(
        "ix_password_reset_tokens_user_id_unused",
        "password_reset_tokens",
        ["user_id"],
        postgresql_where=sa.text("used_at is null"),
    )

    # 0001 建立的 set_updated_at() 沿用,新表也要掛上
    op.execute(
        "create trigger trg_password_reset_tokens_set_updated_at "
        "before update on password_reset_tokens "
        "for each row execute function set_updated_at()"
    )


def downgrade() -> None:
    op.execute(
        "drop trigger if exists trg_password_reset_tokens_set_updated_at "
        "on password_reset_tokens"
    )
    op.drop_index("ix_password_reset_tokens_user_id_unused", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    op.drop_constraint("ck_users_failed_login_attempts_non_negative", "users", type_="check")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_attempts")
