"""Company Layer - Create board governance tables

Revision ID: 20260311_003_create_board_governance_tables
Revises: 20260311_002_create_external_agent_tables
Create Date: 2026-03-11

Creates the board_decisions table for governance approval queue.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from typing import Any


# revision identifiers
revision = "20260311_003_create_board_governance_tables"
down_revision = "20260311_002_create_external_agent_tables"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # =========================================================================
    # BOARD DECISIONS TABLE
    # =========================================================================
    op.create_table(
        "board_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("board_role", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("action_context", postgresql.JSONB, server_default="{}"),
        sa.Column(
            "goal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column(
            "decided_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    op.create_index("idx_board_decisions_tenant", "board_decisions", ["tenant_id"])
    op.create_index("idx_board_decisions_company", "board_decisions", ["company_id"])
    op.create_index("idx_board_decisions_queue", "board_decisions", ["tenant_id", "company_id", "decision"])
    op.create_index("idx_board_decisions_goal", "board_decisions", ["goal_id"])
    
    # PostgreSQL-specific RLS policy
    if _is_postgresql():
        op.execute("ALTER TABLE board_decisions ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY board_decisions_tenant_isolation ON board_decisions
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
        """
        )


def downgrade() -> None:
    op.drop_table("board_decisions")
