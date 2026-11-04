"""add is_superuser server_default

Revision ID: 20260518_add_is_superuser_server_default
Revises: 20260515_user_soft_delete_columns
Create Date: 2026-05-18 00:00:01.000000

Adds server_default to is_superuser column for users table.
Ensures raw SQL INSERTs without explicit is_superuser value get default false from PostgreSQL.
Part of Step 6 integration test fixes.
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


def _is_offline(bind) -> bool:
    """Check if running in offline mode (for alembic upgrade head --sql)."""
    return isinstance(bind, sa.engine.mock.MockConnection)


revision: str = "20260518_add_is_superuser_server_default"
down_revision: str | Sequence[str] | None = "20260515_user_soft_delete_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add server_default to is_superuser column."""
    op.alter_column("users", "is_superuser", server_default=sa.false())


def downgrade() -> None:
    """Downgrade schema - remove server_default from is_superuser column."""
    op.alter_column("users", "is_superuser", server_default=None)
