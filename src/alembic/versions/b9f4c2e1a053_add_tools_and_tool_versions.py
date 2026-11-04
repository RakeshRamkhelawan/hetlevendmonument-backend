"""add_tools_and_tool_versions

Revision ID: b9f4c2e1a053
Revises: ade5f970f820
Create Date: 2026-05-28 23:00:00.000000

SP-B02: Tool Broker CRUD tables.
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "b9f4c2e1a053"
down_revision: str | None = "ade5f970f820"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tools",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("tool_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true"), nullable=False),
        sa.Column("version", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code", sa.Text, nullable=True),
        sa.Column("endpoint_url", sa.String(2000), nullable=True),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("timeout_seconds", sa.Integer, server_default=sa.text("30"), nullable=False),
        sa.Column("retry_policy", JSONB, nullable=True),
        sa.Column("usage_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("created_by", sa.Integer, nullable=True),
    )
    op.create_index("ix_tools_tenant_id", "tools", ["tenant_id"])
    op.create_index("ix_tools_tenant_deleted", "tools", ["tenant_id", "deleted_at"])

    op.create_table(
        "tool_versions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "tool_id",
            sa.Integer,
            sa.ForeignKey("tools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )
    op.create_index("ix_tool_versions_tool_id", "tool_versions", ["tool_id"])
    op.create_index("ix_tool_versions_tenant_id", "tool_versions", ["tenant_id"])

    # RLS -- guard against un-initialized setting with NULLIF
    _rls = "NULLIF(current_setting('app.current_tenant', true), '')::integer"
    op.execute("ALTER TABLE tools ENABLE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY tools_tenant_isolation ON tools USING (tenant_id = {_rls})")
    op.execute("ALTER TABLE tool_versions ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tool_versions_tenant_isolation ON tool_versions USING (tenant_id = {_rls})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tool_versions_tenant_isolation ON tool_versions")
    op.execute("DROP POLICY IF EXISTS tools_tenant_isolation ON tools")
    op.drop_table("tool_versions")
    op.drop_table("tools")
