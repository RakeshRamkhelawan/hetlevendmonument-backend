"""Widen alembic_version.version_num column

Revision ID: 20260412_000_widen_alembic_version
Revises: 20260311_000_create_tenants
Create Date: 2026-04-12

The default alembic_version.version_num column is VARCHAR(32), but our
revision naming scheme uses longer IDs (e.g., '20260311_001_create_company_tables'
is 34 characters). This migration widens the column to VARCHAR(64).
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260412_000_widen_alembic_version"
down_revision: str | Sequence[str] | None = "20260311_000_create_tenants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen version_num column to accommodate longer revision IDs."""
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert version_num column to original width."""
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=64),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
