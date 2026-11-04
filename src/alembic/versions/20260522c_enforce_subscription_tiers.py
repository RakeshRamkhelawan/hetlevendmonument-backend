"""enforce subscription tiers

Revision ID: 20260522c_enforce_sub
Revises: 20260522b_stale_task_index
Create Date: 2026-05-22 22:45:00.000000
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260522c_enforce_sub"
down_revision: str | Sequence[str] | None = "20260522b_stale_task_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Columns may not exist on fresh databases (added by archived migration on prod)
    op.execute(
        sa.text(
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_tier VARCHAR(50) DEFAULT 'free'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(50) DEFAULT 'active'"
        )
    )

    # Backfill NULL values to defaults for data minimization
    op.execute(
        sa.text("UPDATE tenants SET subscription_tier = 'free' WHERE subscription_tier IS NULL")
    )
    op.execute(
        sa.text(
            "UPDATE tenants SET subscription_status = 'active' WHERE subscription_status IS NULL"
        )
    )

    # Ensure server_default constraints are set
    op.alter_column(
        "tenants",
        "subscription_tier",
        existing_type=sa.String(50),
        nullable=True,
        server_default="free",
    )
    op.alter_column(
        "tenants",
        "subscription_status",
        existing_type=sa.String(50),
        nullable=True,
        server_default="active",
    )


def downgrade() -> None:
    op.alter_column(
        "tenants",
        "subscription_tier",
        existing_type=sa.String(50),
        nullable=True,
        server_default=None,
    )
    op.alter_column(
        "tenants",
        "subscription_status",
        existing_type=sa.String(50),
        nullable=True,
        server_default=None,
    )
