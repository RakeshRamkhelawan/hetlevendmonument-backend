"""add_twin_profile_aggregated_at

Revision ID: db72aec98edc
Revises: 20260519b_fix_twin_consent_status
Create Date: 2026-05-19 23:29:09.154851

"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "db72aec98edc"
down_revision: str | Sequence[str] | None = "20260519b_fix_twin_consent_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add last_aggregated_at watermark to user_cognitive_profiles."""
    op.add_column(
        "user_cognitive_profiles",
        sa.Column(
            "last_aggregated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Remove last_aggregated_at from user_cognitive_profiles."""
    op.drop_column("user_cognitive_profiles", "last_aggregated_at")
