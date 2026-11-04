"""Add export_jobs table for GDPR data export tracking

Revision ID: 20260528b
Revises: 20260528a
Create Date: 2026-05-28

AUDIT-P0-F1: ExportJob ORM model + Alembic migration
ADR-005: tenant_id NOT NULL + RLS policy
ADR-019: created_at uses clock_timestamp() for serializable ordering
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260528b"
down_revision = "20260528a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("export_format", sa.String(20), nullable=False),
        sa.Column("result_url", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_export_jobs_tenant_id", "export_jobs", ["tenant_id"])
    op.execute("ALTER TABLE export_jobs ENABLE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY tenant_isolation_policy ON export_jobs
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer);
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON export_jobs;")
    op.drop_index("ix_export_jobs_tenant_id", table_name="export_jobs")
    op.drop_table("export_jobs")
