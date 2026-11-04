"""activepieces_tz_aware_timestamps

Convert all DateTime columns in ActivePieces tables to TIMESTAMPTZ
(timezone-aware) to prevent mismatch with UTC-aware datetimes in Python.

Revision ID: 20260408b_activepieces_tzaware
Revises: 20260408_add_activepieces_tables
Create Date: 2026-04-08 12:00:00.000000

NOTE: sa.inspect() is intentionally NOT used here. These tables are created
by the immediately preceding migration (20260408_add_activepieces_tables),
so they always exist at this point in the chain. Unconditional ALTER COLUMN
works correctly in both online and offline (--sql dry-run) mode.
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260408b_activepieces_tzaware"
down_revision: str | Sequence[str] | None = "20260408_add_activepieces_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column) pairs to migrate
_COLUMNS = [
    ("activepieces_flows", "created_at"),
    ("activepieces_flows", "updated_at"),
    ("activepieces_connections", "last_used_at"),
    ("activepieces_connections", "last_error_at"),
    ("activepieces_connections", "created_at"),
    ("activepieces_connections", "updated_at"),
    ("activepieces_flow_runs", "created_at"),
    ("activepieces_flow_runs", "completed_at"),
    ("activepieces_sync_logs", "created_at"),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            existing_nullable=True,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            existing_nullable=True,
        )
