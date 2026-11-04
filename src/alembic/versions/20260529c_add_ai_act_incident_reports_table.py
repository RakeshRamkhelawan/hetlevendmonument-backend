"""add ai_act_incident_reports table

EU AI Act Article 62 -- serious incident reporting with 10-year retention.
Soft-delete only (deleted_at) -- NEVER hard delete this table.

Revision ID: 20260529c
Revises: 20260529b
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260529c"
down_revision = "20260529b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_act_incident_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("incident_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("agent_name", sa.String(255), nullable=True),
        sa.Column("eu_reporting_required", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("eu_reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_status", sa.String(50), nullable=False, server_default="open"),
        sa.Column("incident_data", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_incident_tenant_created",
        "ai_act_incident_reports",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_incident_tenant_status",
        "ai_act_incident_reports",
        ["tenant_id", "resolution_status"],
    )
    op.create_index(
        "ix_incident_tenant_id",
        "ai_act_incident_reports",
        ["tenant_id"],
    )

    op.execute(sa.text("ALTER TABLE ai_act_incident_reports ENABLE ROW LEVEL SECURITY;"))
    op.execute(
        sa.text(
            "CREATE POLICY tenant_isolation ON ai_act_incident_reports "
            "USING (tenant_id = current_setting('app.current_tenant', TRUE)::integer);"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON ai_act_incident_reports;"))
    op.drop_index("ix_incident_tenant_id", table_name="ai_act_incident_reports")
    op.drop_index("ix_incident_tenant_status", table_name="ai_act_incident_reports")
    op.drop_index("ix_incident_tenant_created", table_name="ai_act_incident_reports")
    op.drop_table("ai_act_incident_reports")
