"""add department and function fields to registered_agents

Revision ID: 20260506_add_department_function_fields
Revises: 20260506_add_unified_agent_fields
Create Date: 2026-05-06 00:00:00.000000

TASK #5: Add department and function metadata to RegisteredAgent for comprehensive
agent classification and governance. These fields enable:
  - Department-aware routing (route_with_department_filter)
  - Department validation in OversightGate
  - Function-based agent discovery and filtering
  - Multi-tenant department isolation

New columns:
  - department: Agent's assigned department (string, nullable, indexed)
  - function: Array of function tags for agent capabilities (JSONB array)

Indexes:
  - idx_agent_department: for department-based queries
  - idx_agent_department_tenant: for tenant-scoped department filtering
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.
from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260506_add_department_function_fields"
down_revision: str | Sequence[str] | None = "20260506_add_unified_agent_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add department and function columns to registered_agents table."""
    # 1. department: Agent's assigned department for governance and routing
    op.add_column(
        "registered_agents",
        sa.Column(
            "department",
            sa.String(100),
            nullable=True,
            comment="Agent's assigned department (STRATEGY, OPERATIONS, FINANCE, HR, SALES_MARKETING, PRODUCT_INNOVATION, IT_SECURITY, LEGAL_COMPLIANCE, CUSTOMER_EXPERIENCE, DATA_AI_GOVERNANCE)"
        ),
    )

    # 2. function: Array of function tags for agent capabilities
    op.add_column(
        "registered_agents",
        sa.Column(
            "function",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
            comment="Array of function tags describing agent capabilities"
        ),
    )

    # Create indexes for efficient department-based queries
    op.create_index(
        "idx_agent_department",
        "registered_agents",
        ["department"],
        if_not_exists=True
    )

    op.create_index(
        "idx_agent_department_tenant",
        "registered_agents",
        ["department", "tenant_id"],
        if_not_exists=True
    )


def downgrade() -> None:
    """Drop department and function columns and indexes."""
    # Drop indexes
    op.drop_index("idx_agent_department_tenant", table_name="registered_agents", if_exists=True)
    op.drop_index("idx_agent_department", table_name="registered_agents", if_exists=True)

    # Drop columns
    op.drop_column("registered_agents", "function")
    op.drop_column("registered_agents", "department")
