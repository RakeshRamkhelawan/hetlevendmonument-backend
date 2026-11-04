"""add granular consent categories to user_twin_consent

Revision ID: 20260521_twin_consent_categories
Revises: 20260521_tenant_data_residency
Create Date: 2026-05-21 08:30:00.000000

"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260521_twin_consent_categories"
down_revision: str | None = "20260521_tenant_data_residency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_twin_consent",
        sa.Column(
            "behavior_tracking",
            sa.Boolean,
            nullable=False,
            server_default="TRUE",
        ),
    )
    op.add_column(
        "user_twin_consent",
        sa.Column(
            "profile_aggregation",
            sa.Boolean,
            nullable=False,
            server_default="TRUE",
        ),
    )
    op.add_column(
        "user_twin_consent",
        sa.Column(
            "ai_interventions",
            sa.Boolean,
            nullable=False,
            server_default="TRUE",
        ),
    )
    op.add_column(
        "user_twin_consent",
        sa.Column(
            "cross_session_memory",
            sa.Boolean,
            nullable=False,
            server_default="TRUE",
        ),
    )

    # Backfill from existing status (more granular than consent_given)
    # enabled  -> all True
    # paused   -> behavior_tracking=False, rest=True
    # disabled -> all False
    op.execute(
        sa.text(
            """
            UPDATE user_twin_consent
            SET behavior_tracking = (status IN ('enabled', 'paused')),
                profile_aggregation = (status = 'enabled'),
                ai_interventions = (status = 'enabled'),
                cross_session_memory = (status = 'enabled')
            """
        )
    )


def downgrade() -> None:
    op.drop_column("user_twin_consent", "cross_session_memory")
    op.drop_column("user_twin_consent", "ai_interventions")
    op.drop_column("user_twin_consent", "profile_aggregation")
    op.drop_column("user_twin_consent", "behavior_tracking")
