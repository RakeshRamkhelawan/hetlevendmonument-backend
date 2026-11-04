"""Add hitl_tickets table for persistent HITL ticket storage.

Revision ID: 20260525c
Revises: 20260525b
Create Date: 2026-05-25

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260525c"
down_revision: str | Sequence[str] | None = "20260525b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _is_offline() -> bool:
    import sqlalchemy.engine.mock as mock_mod

    return isinstance(op.get_bind(), mock_mod.MockConnection)


def upgrade() -> None:
    op.create_table(
        "hitl_tickets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticket_ref", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("tool_name", sa.String(length=256), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_ref"),
    )
    op.create_index("ix_hitl_tickets_ticket_ref", "hitl_tickets", ["ticket_ref"], unique=True)
    op.create_index("ix_hitl_tickets_tenant_id", "hitl_tickets", ["tenant_id"])
    op.create_index(
        "ix_hitl_tickets_tenant_status",
        "hitl_tickets",
        ["tenant_id", "status"],
    )

    if _is_postgresql() and not _is_offline():
        op.execute(sa.text("ALTER TABLE hitl_tickets ENABLE ROW LEVEL SECURITY"))
        op.execute(
            sa.text(
                "CREATE POLICY hitl_tickets_tenant_isolation ON hitl_tickets "
                "FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )


def downgrade() -> None:
    if _is_postgresql() and not _is_offline():
        op.execute(sa.text("DROP POLICY IF EXISTS hitl_tickets_tenant_isolation ON hitl_tickets"))
        op.execute(sa.text("ALTER TABLE hitl_tickets DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_hitl_tickets_tenant_status", table_name="hitl_tickets")
    op.drop_index("ix_hitl_tickets_tenant_id", table_name="hitl_tickets")
    op.drop_index("ix_hitl_tickets_ticket_ref", table_name="hitl_tickets")
    op.drop_table("hitl_tickets")
