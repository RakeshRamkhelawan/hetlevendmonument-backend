"""create audit_report_jobs table

Revision ID: 20260525a
Revises: 20260524f
Create Date: 2026-05-25 10:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260525a"
down_revision: str | Sequence[str] | None = "20260524f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # create table
    op.create_table(
        "audit_report_jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("progress_pct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_url", sa.String(1000), nullable=True),
        sa.Column("from_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index(
        "ix_audit_report_jobs_tenant_id",
        "audit_report_jobs",
        ["tenant_id"],
    )

    # enable row-level security
    op.execute("ALTER TABLE audit_report_jobs ENABLE ROW LEVEL SECURITY;")

    # create RLS policy
    op.execute(
        """
        CREATE POLICY tenant_isolation_policy ON audit_report_jobs
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::integer);
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON audit_report_jobs;")
    op.drop_index("ix_audit_report_jobs_tenant_id", table_name="audit_report_jobs")
    op.drop_table("audit_report_jobs")
