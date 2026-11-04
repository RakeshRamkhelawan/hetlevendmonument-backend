"""Company Layer - Expand: Add company fields to existing tables (ZERO-DOWNTIME Step 1)

Revision ID: 20260311_006a_expand_add_company_fields
Revises: 20260311_005_create_pack_activation_audit_log
Create Date: 2026-03-11

EXPAND phase of expand-contract pattern:
Adds nullable columns to existing tables WITHOUT foreign key constraints.
Application code will write to BOTH old and new columns during transition.

After this migration:
1. Deploy application that writes to both columns
2. Run backfill migration (006b) to populate existing data
3. After successful deployment, run contract migration (006c) to add FK constraints
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from typing import Any

from alembic import op


# revision identifiers
revision = "20260311_006a_expand_add_company_fields"
down_revision = "20260311_005_create_pack_activation_audit_log"
branch_labels = None
depends_on = None


def _is_offline(conn: object) -> bool:
    """Return True when running in Alembic offline (--sql) mode."""
    return isinstance(conn, sa.engine.mock.MockConnection)


def upgrade() -> None:
    # =========================================================================
    # EXPAND: Add nullable columns (no FK constraints yet)
    # =========================================================================
    conn = op.get_bind()
    offline = _is_offline(conn)

    if offline:
        inspector_tables: list[Any] = []  # TODO(TYPE): replace with concrete type
    else:
        inspector_tables = sa.inspect(conn).get_table_names()

    # Add goal_id to procedure_executions (if table exists)
    # procedure_executions is created by company tables migrations; may not exist
    # in all test databases (e.g. SQLite in-memory CI).
    if offline or "procedure_executions" in inspector_tables:
        op.add_column(
            "procedure_executions",
            sa.Column(
                "goal_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="Reference to goals table (will be FK in contract phase)",
            ),
        )
        op.create_index("idx_procedure_executions_goal", "procedure_executions", ["goal_id"])

    # Add company_id to domain_packs (if table exists)
    # Note: domain_packs might not exist as a table, could be in YAML only.
    if offline or "domain_packs" in inspector_tables:
        op.add_column(
            "domain_packs",
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="Reference to companies table (will be FK in contract phase)",
            ),
        )
        op.create_index("idx_domain_packs_company", "domain_packs", ["company_id"])


def downgrade() -> None:
    # Remove the columns added in upgrade
    conn = op.get_bind()
    offline = _is_offline(conn)

    if offline:
        inspector_tables: list[Any] = []  # TODO(TYPE): replace with concrete type
    else:
        inspector_tables = sa.inspect(conn).get_table_names()

    if offline or "domain_packs" in inspector_tables:
        op.drop_index("idx_domain_packs_company", table_name="domain_packs")
        op.drop_column("domain_packs", "company_id")

    if offline or "procedure_executions" in inspector_tables:
        op.drop_index("idx_procedure_executions_goal", table_name="procedure_executions")
        op.drop_column("procedure_executions", "goal_id")
