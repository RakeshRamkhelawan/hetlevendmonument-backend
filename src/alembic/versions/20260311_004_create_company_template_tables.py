"""Company Layer - Create company template tables

Revision ID: 20260311_004_create_company_template_tables
Revises: 20260311_003_create_board_governance_tables
Create Date: 2026-03-11

Creates the company_templates table for reusable company configurations.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from typing import Any


# revision identifiers
revision = "20260311_004_create_company_template_tables"
down_revision = "20260311_003_create_board_governance_tables"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # =========================================================================
    # COMPANY TEMPLATES TABLE
    # =========================================================================
    op.create_table(
        "company_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("company_type", sa.String(20), nullable=False),
        sa.Column("sector", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("template_definition", postgresql.JSONB, server_default="{}"),
        sa.Column("is_platform_template", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "contributed_by_tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_sum", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    op.create_index("idx_company_templates_contributor", "company_templates", ["contributed_by_tenant_id"])
    op.create_index("idx_company_templates_type_sector", "company_templates", ["company_type", "sector"])
    
    # PostgreSQL-specific RLS policies
    if _is_postgresql():
        op.execute("ALTER TABLE company_templates ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY company_templates_tenant_isolation ON company_templates
            FOR ALL USING (
                is_platform_template = true OR
                contributed_by_tenant_id = current_setting('app.current_tenant')::INTEGER
            )
        """
        )

        # Note: Platform templates are visible to all tenants
        op.execute(
            """
            CREATE POLICY company_templates_platform ON company_templates
            FOR SELECT USING (is_platform_template = true)
        """
        )


def downgrade() -> None:
    op.drop_table("company_templates")
