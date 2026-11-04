"""Fix twin RLS policies to use safe NULLIF pattern

Revision ID: 20260523b_fix_twin_rls_safe_pattern
Revises: 20260523a_council
Create Date: 2026-05-23 15:30:00.000000

Problem:
    Twin RLS policies (created in 20260519a_add_twin_rls_policies.py) use:
        current_setting('app.current_tenant')::INTEGER
    This crashes with 'current_setting() missing' when the session variable
    is not set (worker processes, migrations, admin queries).

Fix:
    Drop the old policies and recreate with the safe pattern used by core tables:
        NULLIF(current_setting('app.current_tenant', true), '')::INTEGER
    This returns NULL when missing, causing deny-by-default (fail-secure).

Tables affected:
    - user_behavior_observations
    - user_cognitive_profiles
    - user_twin_consent
    - focus_builder_accepted_workflows
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260523b_fix_twin_rls_safe_pattern"
down_revision: str | Sequence[str] | None = "20260523a_council"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = [
    "user_behavior_observations",
    "user_cognitive_profiles",
    "user_twin_consent",
    "focus_builder_accepted_workflows",
]


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for tbl in _TABLES:
        # Drop old crash-prone policy
        op.execute(sa.text(f"DROP POLICY IF EXISTS twin_{tbl}_tenant_isolation ON {tbl}"))
        # Recreate with safe NULLIF pattern (deny-by-default when missing)
        op.execute(
            sa.text(
                f"CREATE POLICY twin_{tbl}_tenant_isolation ON {tbl} "
                f"FOR ALL USING ("
                f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                f")"
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for tbl in _TABLES:
        # Drop safe policy
        op.execute(sa.text(f"DROP POLICY IF EXISTS twin_{tbl}_tenant_isolation ON {tbl}"))
        # Recreate old crash-prone pattern
        op.execute(
            sa.text(
                f"CREATE POLICY twin_{tbl}_tenant_isolation ON {tbl} "
                f"FOR ALL USING ("
                f"tenant_id = current_setting('app.current_tenant')::INTEGER"
                f")"
            )
        )
