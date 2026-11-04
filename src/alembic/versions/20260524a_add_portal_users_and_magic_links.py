"""add_portal_users_and_magic_links

Revision ID: 20260524a
Revises: 20260523g_add_quiet_hours_timezone
Create Date: 2026-05-24 08:15:00

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260524a"
down_revision: str | Sequence[str] | None = "20260523g_add_quiet_hours_timezone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ["portal_users", "magic_link_tokens"]


def _is_postgresql() -> bool:
    return op.get_context().dialect.name == "postgresql"


def _enable_rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"CREATE POLICY {table}_tenant_isolation ON {table} "
            f"FOR ALL USING ("
            f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
            f")"
        )
    )


def _disable_rls(table: str) -> None:
    op.execute(sa.text(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}"))
    op.execute(sa.text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def upgrade() -> None:
    op.create_table(
        "portal_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False),
        sa.Column("is_blocked", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pu_tenant_email", "portal_users", ["tenant_id", "email"], unique=True
    )
    op.create_index(
        op.f("ix_portal_users_tenant_id"),
        "portal_users",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "magic_link_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("portal_user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["portal_user_id"], ["portal_users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_mlt_expires", "magic_link_tokens", ["expires_at"], unique=False
    )
    op.create_index(
        "idx_mlt_tenant_user",
        "magic_link_tokens",
        ["tenant_id", "portal_user_id"],
        unique=False,
    )

    if _is_postgresql():
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    if _is_postgresql():
        for tbl in reversed(_RLS_TABLES):
            _disable_rls(tbl)

    op.drop_index("idx_mlt_tenant_user", table_name="magic_link_tokens")
    op.drop_index("idx_mlt_expires", table_name="magic_link_tokens")
    op.drop_table("magic_link_tokens")
    op.drop_index(op.f("ix_portal_users_tenant_id"), table_name="portal_users")
    op.drop_index("idx_pu_tenant_email", table_name="portal_users")
    op.drop_table("portal_users")
