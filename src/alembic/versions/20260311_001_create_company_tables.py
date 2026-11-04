"""Company Layer - Create company tables

Revision ID: 20260311_001_create_company_tables
Revises: 20260310_memory_traces_snapshots
Create Date: 2026-03-11

Creates the core Company Layer tables:
- companies
- departments
- goals

With indexes for tenant isolation and query performance.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from typing import Any


# revision identifiers
revision = "20260311_001_create_company_tables"
down_revision = "20260412_000_widen_alembic_version"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # =========================================================================
    # 1. COMPANIES TABLE
    # =========================================================================
    op.create_table(  # noqa: create-table
        "companies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer,
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("company_type", sa.String(20), nullable=False, server_default="mkb"),
        sa.Column("sector", sa.String(100), nullable=False),
        sa.Column("mission", sa.Text, nullable=True),
        sa.Column("config", postgresql.JSONB, server_default="{}"),
        sa.Column("board_role_config", postgresql.JSONB, nullable=True),
        # Note: template_id FK to company_templates removed for now
        # sa.Column(
        #     "template_id",
        #     postgresql.UUID(as_uuid=True),
        #     sa.ForeignKey("company_templates.id", ondelete="SET NULL"),
        #     nullable=True,
        # ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_companies_tenant", "companies", ["tenant_id"])

    # PostgreSQL-specific RLS policy
    if _is_postgresql():
        op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY companies_tenant_isolation ON companies
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
        """
        )

    # =========================================================================
    # 2. DEPARTMENTS TABLE
    # =========================================================================
    op.create_table(  # noqa: create-table
        "departments",
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
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "parent_department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "head_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("board_role", sa.String(50), nullable=True),
        sa.Column("budget_monthly_tokens", sa.Integer, nullable=True),
        sa.Column("domain_pack_ids", postgresql.JSONB, server_default="[]"),
        sa.Column("config", postgresql.JSONB, server_default="{}"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_departments_tenant", "departments", ["tenant_id"])
    op.create_index("idx_departments_company", "departments", ["company_id"])
    op.create_index("idx_departments_parent", "departments", ["parent_department_id"])

    # PostgreSQL-specific RLS policy
    if _is_postgresql():
        op.execute("ALTER TABLE departments ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY departments_tenant_isolation ON departments
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
        """
        )

    # =========================================================================
    # 3. GOALS TABLE
    # =========================================================================
    op.create_table(  # noqa: create-table
        "goals",
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
            "parent_goal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("goals.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("goal_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("kpis", postgresql.JSONB, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("progress_pct", sa.Integer, nullable=False, server_default="0"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index("idx_goals_tenant", "goals", ["tenant_id"])
    op.create_index("idx_goals_company", "goals", ["company_id"])
    op.create_index("idx_goals_parent", "goals", ["parent_goal_id"])
    op.create_index("idx_goals_department", "goals", ["department_id"])

    # PostgreSQL-specific RLS policy
    if _is_postgresql():
        op.execute("ALTER TABLE goals ENABLE ROW LEVEL SECURITY")
        op.execute(
            """
            CREATE POLICY goals_tenant_isolation ON goals
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
        """
        )


def downgrade() -> None:
    # Reverse order for safe downgrade
    op.drop_table("goals")
    op.drop_table("departments")
    op.drop_table("companies")
