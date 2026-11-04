"""add_foundation_portal_settings

Revision ID: 20260524c
Revises: 20260524b
Create Date: 2026-05-24 08:17:00

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260524c"
down_revision: str | Sequence[str] | None = "20260524b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ["foundation_portal_settings"]


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
        "foundation_portal_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("platform_name_nl", sa.String(length=120), nullable=False),
        sa.Column("platform_name_en", sa.String(length=120), nullable=True),
        sa.Column("primary_color", sa.String(length=7), nullable=False),
        sa.Column("accent_color", sa.String(length=7), nullable=False),
        sa.Column("logo_url", sa.String(length=1024), nullable=True),
        sa.Column("favicon_url", sa.String(length=1024), nullable=True),
        sa.Column("guidelines_nl", sa.Text(), nullable=True),
        sa.Column("guidelines_en", sa.Text(), nullable=True),
        sa.Column("about_nl", sa.Text(), nullable=True),
        sa.Column("about_en", sa.Text(), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
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
        sa.UniqueConstraint("tenant_id"),
    )

    if _is_postgresql():
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    if _is_postgresql():
        for tbl in reversed(_RLS_TABLES):
            _disable_rls(tbl)
    op.drop_table("foundation_portal_settings")
