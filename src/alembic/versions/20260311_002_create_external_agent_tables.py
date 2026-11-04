"""Company Layer - Create external agent tables

Revision ID: 20260311_002_create_external_agent_tables
Revises: 20260311_001_create_company_tables
Create Date: 2026-03-11

Creates the external_agents table for the heartbeat protocol.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from typing import Any


# revision identifiers
revision = "20260311_002_create_external_agent_tables"
down_revision = "20260311_001_create_company_tables"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # =========================================================================
    # EXTERNAL AGENTS TABLE
    # =========================================================================
    op.create_table(
        "external_agents",
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
            nullable=True,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("runtime", sa.String(100), nullable=False),
        sa.Column("capabilities", postgresql.JSONB, server_default="[]"),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("api_key_hash", sa.String(255), nullable=False),
        sa.Column("heartbeat_interval_seconds", sa.Integer, nullable=False, server_default="30"),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="registered"),
        sa.Column("metrics", postgresql.JSONB, server_default="{}"),
        sa.Column("config", postgresql.JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    op.create_index("idx_external_agents_tenant", "external_agents", ["tenant_id"])
    op.create_index("idx_external_agents_tenant_status", "external_agents", ["tenant_id", "status"])
    op.create_index("idx_external_agents_company", "external_agents", ["company_id"])
    
    # PostgreSQL-specific RLS policy
    if _is_postgresql():
        op.execute("ALTER TABLE external_agents ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY external_agents_tenant_isolation ON external_agents
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
        """
        )


def downgrade() -> None:
    op.drop_table("external_agents")
