"""add_workflow_snapshots

Revision ID: 20260528c
Revises: 93475c4a00a0
Create Date: 2026-05-28 23:30:00.000000

SP-E02: JSON workflow snapshots for real-time collaboration.
"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "20260528c"
down_revision: str | None = "93475c4a00a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workflow_snapshots table with RLS."""
    op.create_table(
        "workflow_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workflow_id", sa.String(200), nullable=False),
        sa.Column("snapshot_data", JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_snapshots_tenant_id",
        "workflow_snapshots",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_snapshots_workflow_id",
        "workflow_snapshots",
        ["workflow_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_snapshots_tenant_workflow",
        "workflow_snapshots",
        ["tenant_id", "workflow_id"],
        unique=False,
    )

    # ADR-005: Enable RLS
    op.execute("ALTER TABLE workflow_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON workflow_snapshots "
        "FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer)"
    )


def downgrade() -> None:
    """Drop workflow_snapshots table."""
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON workflow_snapshots")
    op.execute("ALTER TABLE workflow_snapshots DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_workflow_snapshots_tenant_workflow", table_name="workflow_snapshots")
    op.drop_index("ix_workflow_snapshots_workflow_id", table_name="workflow_snapshots")
    op.drop_index("ix_workflow_snapshots_tenant_id", table_name="workflow_snapshots")
    op.drop_table("workflow_snapshots")
