"""add agent_configs table
Revision ID: 20260529e
Revises: 20260529d
Create Date: 2026-05-29
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260529e"
down_revision = "20260529d"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "agent_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_type", sa.String(100), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("department", sa.String(50), nullable=True),
        sa.Column("subscribed_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_agent_config_active", "agent_configs", ["tenant_id", "is_active"])
    op.create_index("idx_agent_config_agent_id", "agent_configs", ["tenant_id", "agent_id"], unique=True)
    op.create_index("idx_agent_config_department", "agent_configs", ["department"])
    op.execute(sa.text("ALTER TABLE agent_configs ENABLE ROW LEVEL SECURITY;"))
    op.execute(sa.text("CREATE POLICY tenant_isolation ON agent_configs USING (tenant_id = current_setting('app.current_tenant', TRUE)::integer);"))

def downgrade() -> None:
    op.execute(sa.text("DROP POLICY IF EXISTS tenant_isolation ON agent_configs;"))
    op.drop_index("idx_agent_config_department", table_name="agent_configs")
    op.drop_index("idx_agent_config_agent_id", table_name="agent_configs")
    op.drop_index("idx_agent_config_active", table_name="agent_configs")
    op.drop_table("agent_configs")
