"""Add quiet_hours_timezone to user_notification_preferences

Revision ID: 20260523g_add_quiet_hours_timezone
Revises: 20260523f_decision_contests
Create Date: 2026-05-23 21:40:00.000000
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

import sqlalchemy as sa

from alembic import op

revision = "20260523g_add_quiet_hours_timezone"
down_revision = "20260523f_decision_contests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_offline = isinstance(bind, sa.engine.mock.MockConnection)

    if is_offline:
        op.execute(
            sa.text(
                "-- ALTER TABLE user_notification_preferences "
                "ADD COLUMN quiet_hours_timezone VARCHAR(63) NOT NULL DEFAULT 'UTC';"
            )
        )
    else:
        op.add_column(
            "user_notification_preferences",
            sa.Column(
                "quiet_hours_timezone",
                sa.String(63),
                nullable=False,
                server_default=sa.text("'UTC'"),
            ),
        )


def downgrade() -> None:
    op.drop_column("user_notification_preferences", "quiet_hours_timezone")
