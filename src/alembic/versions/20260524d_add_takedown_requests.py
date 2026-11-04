"""add_takedown_requests

Revision ID: 20260524d
Revises: 20260524c
Create Date: 2026-05-24 08:18:00

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260524d"
down_revision: str | Sequence[str] | None = "20260524c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ["takedown_requests"]


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
        "takedown_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("requester_email", sa.String(length=255), nullable=False),
        sa.Column("requester_name", sa.String(length=255), nullable=False),
        sa.Column("legal_basis", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "APPROVED", "REJECTED", "ESCALATED", name="takedown_status_enum"
            ),
            nullable=False,
        ),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["content_id"], ["foundation_content.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_td_tenant_status", "takedown_requests", ["tenant_id", "status"], unique=False
    )
    op.create_index(
        op.f("ix_takedown_requests_content_id"),
        "takedown_requests",
        ["content_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_takedown_requests_tenant_id"),
        "takedown_requests",
        ["tenant_id"],
        unique=False,
    )

    if _is_postgresql():
        for tbl in _RLS_TABLES:
            _enable_rls(tbl)


def downgrade() -> None:
    if _is_postgresql():
        for tbl in reversed(_RLS_TABLES):
            _disable_rls(tbl)

    op.drop_index(
        op.f("ix_takedown_requests_tenant_id"), table_name="takedown_requests"
    )
    op.drop_index(
        op.f("ix_takedown_requests_content_id"), table_name="takedown_requests"
    )
    op.drop_index("idx_td_tenant_status", table_name="takedown_requests")
    op.drop_table("takedown_requests")
    op.execute("DROP TYPE IF EXISTS takedown_status_enum")
