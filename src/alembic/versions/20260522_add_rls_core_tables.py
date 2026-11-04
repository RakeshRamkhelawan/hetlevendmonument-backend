"""Add RLS policies to core tenant tables (users, agents, registered_agents, tool_audit_logs)

Revision ID: 20260522_add_rls_core_tables
Revises: 20260521c_twin_suggestion_log_and_budget
Create Date: 2026-05-22

audit_logs is intentionally excluded: it is outside the ORM auto-filter by design
(documented in CLAUDE.md valkuilen-tabel) and uses a fail-secure RuntimeError pattern.
user_roles junction table has no tenant_id column and is excluded.
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260522_add_rls_core_tables"
down_revision: str | Sequence[str] | None = "20260521c_twin_suggestion_log_and_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ["users", "agents", "registered_agents", "tool_audit_logs"]


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for tbl in _TABLES:
        op.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        # missing_ok=true: returns NULL when app.current_tenant is not set,
        # so unauthenticated/background sessions see zero rows instead of crashing.
        op.execute(
            sa.text(
                f"CREATE POLICY core_{tbl}_tenant_isolation ON {tbl} "
                f"FOR ALL USING ("
                f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                f")"
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for tbl in _TABLES:
        op.execute(sa.text(f"DROP POLICY IF EXISTS core_{tbl}_tenant_isolation ON {tbl}"))
        op.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
