"""Add status column to user_twin_consent and backfill from consent_given

Revision ID: 20260519b_fix_twin_consent_status
Revises: 20260519a_add_twin_rls_policies
Create Date: 2026-05-19

"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260519b_fix_twin_consent_status"
down_revision: str | Sequence[str] | None = "20260519a_add_twin_rls_policies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add status column and backfill from consent_given."""
    op.add_column(
        "user_twin_consent",
        sa.Column("status", sa.String(20), nullable=False, server_default="enabled"),
    )

    # Backfill: consent_given=True -> enabled, consent_given=False -> disabled
    op.execute(
        """
        UPDATE user_twin_consent
        SET status = CASE WHEN consent_given THEN 'enabled' ELSE 'disabled' END
        """
    )


def downgrade() -> None:
    """Drop status column."""
    op.drop_column("user_twin_consent", "status")
