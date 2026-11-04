"""Add RLS policies to digital twin tables

Revision ID: 20260519a_add_twin_rls_policies
Revises: 20260519_create_digital_twin_tables
Create Date: 2026-05-19

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260519a_add_twin_rls_policies"
down_revision: str | Sequence[str] | None = "20260519_create_digital_twin_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Enable RLS and create tenant isolation policies on digital twin tables."""
    if not _is_postgresql():
        return

    tables = [
        "user_behavior_observations",
        "user_cognitive_profiles",
        "user_twin_consent",
        "focus_builder_accepted_workflows",
    ]

    for tbl in tables:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY twin_{tbl}_tenant_isolation ON {tbl}
            FOR ALL USING (tenant_id = current_setting('app.current_tenant')::INTEGER)
            """
        )


def downgrade() -> None:
    """Drop RLS policies and disable RLS on digital twin tables."""
    if not _is_postgresql():
        return

    tables = [
        "user_behavior_observations",
        "user_cognitive_profiles",
        "user_twin_consent",
        "focus_builder_accepted_workflows",
    ]

    for tbl in tables:
        op.execute(f"DROP POLICY IF EXISTS twin_{tbl}_tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")
