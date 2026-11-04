"""Add agentic_tasks table with tenant isolation.

Revision ID: 20260706_add_agentic_tasks_table
Revises: c3d4e5f6a7b8
Create Date: 2026-07-06

Finding: AGENTIC-COPILOT-TAAKBEHEER-2026-07 Day 2
ADR: ADR-005 (tenant_id NOT NULL + RLS)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260706_add_agentic_tasks_table"
down_revision: str | Sequence[str] | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline() -> bool:
    """Detect Alembic offline (--sql) mode to skip runtime-only DDL."""
    import sqlalchemy.engine.mock as mock_mod

    return isinstance(op.get_bind(), mock_mod.MockConnection)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "agentic_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "priority",
            sa.String(length=20),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("assigned_agent_id", sa.String(length=100), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "parent_task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agentic_tasks.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'failed', 'cancelled')",
            name="ck_agentic_tasks_status",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'critical')",
            name="ck_agentic_tasks_priority",
        ),
    )

    op.create_index(
        "ix_agentic_tasks_tenant_status",
        "agentic_tasks",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_agentic_tasks_tenant_assigned",
        "agentic_tasks",
        ["tenant_id", "assigned_agent_id"],
    )
    op.create_index(
        "ix_agentic_tasks_external_ref",
        "agentic_tasks",
        ["external_ref"],
    )

    if _is_postgresql() and not _is_offline():
        op.execute(sa.text("ALTER TABLE agentic_tasks ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text("DROP POLICY IF EXISTS agentic_task_tenant_isolation ON agentic_tasks"))
        op.execute(
            sa.text(
                "CREATE POLICY agentic_task_tenant_isolation ON agentic_tasks "
                "FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )


def downgrade() -> None:
    if _is_postgresql() and not _is_offline():
        op.execute(sa.text("DROP POLICY IF EXISTS agentic_task_tenant_isolation ON agentic_tasks"))
        op.execute(sa.text("ALTER TABLE agentic_tasks DISABLE ROW LEVEL SECURITY"))

    op.drop_index("ix_agentic_tasks_external_ref", table_name="agentic_tasks")
    op.drop_index("ix_agentic_tasks_tenant_assigned", table_name="agentic_tasks")
    op.drop_index("ix_agentic_tasks_tenant_status", table_name="agentic_tasks")
    op.drop_table("agentic_tasks")
