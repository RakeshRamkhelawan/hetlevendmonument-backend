"""Add RLS policies to C7 workflow engine tables

Revision ID: 20260523c_add_rls_c7_workflow_tables
Revises: 20260523b_fix_twin_rls_safe_pattern
Create Date: 2026-05-23 15:45:00.000000

Scope:
    Enable row-level security on the C7 workflow engine tables.
    These tables contain core business logic and were missing DB-level
    tenant isolation, relying solely on the ORM auto-filter hook.

Tables affected:
    - c7_workflows
    - c7_workflow_executions
    - c7_execution_tasks
    - c7_execution_events

Policy pattern (identical to core tables, fail-secure):
    NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
    Returns NULL when the session variable is not set -> deny-by-default.
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "20260523c_add_rls_c7_workflow_tables"
down_revision: str | Sequence[str] | None = "20260523b_fix_twin_rls_safe_pattern"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "c7_workflows",
    "c7_workflow_executions",
    "c7_execution_tasks",
    "c7_execution_events",
]


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _is_offline(bind: sa.engine.Connection) -> bool:
    """Return True when running in Alembic offline mode."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    if not _is_postgresql():
        return

    bind = op.get_bind()
    if _is_offline(bind):
        existing = set(_TABLES)
    else:
        inspector = sa.inspect(bind)
        existing = set(inspector.get_table_names())

    for tbl in _TABLES:
        if tbl not in existing:
            # Table missing on fresh databases (created by archived migration on prod).
            # RLS will be enabled by 20260522b_stale_task_index which creates the tables.
            continue
        policy_name = f"{tbl}_tenant_isolation"
        op.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {tbl}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {policy_name} ON {tbl} "
                f"FOR ALL USING ("
                f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                f")"
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    bind = op.get_bind()
    if _is_offline(bind):
        existing = set(_TABLES)
    else:
        inspector = sa.inspect(bind)
        existing = set(inspector.get_table_names())

    for tbl in _TABLES:
        if tbl not in existing:
            continue
        policy_name = f"{tbl}_tenant_isolation"
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy_name} ON {tbl}"))
        op.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
