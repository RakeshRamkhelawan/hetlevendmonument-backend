"""user soft delete columns

Revision ID: 20260515_user_soft_delete_columns
Revises: 20260515_fix_c7_workflow_templates
Create Date: 2026-05-15 00:00:02.000000

Adds soft-delete columns to users table for GDPR compliance (DSAR).
Allows users to schedule deletion and track when accounts were deleted.
Part of T2-D: User soft-delete support for privacy requirements.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


def _is_offline(bind) -> bool:
    """Check if running in offline mode (for alembic upgrade head --sql)."""
    return isinstance(bind, sa.engine.mock.MockConnection)


revision: str = "20260515_user_soft_delete_columns"
down_revision: str | Sequence[str] | None = "20260515_fix_c7_workflow_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add soft-delete columns to users table."""
    bind = op.get_bind()

    # Add deleted_at column (if not already present)
    if not _is_offline(bind):
        inspector = sa.inspect(bind)
        columns = [c["name"] for c in inspector.get_columns("users")]
        if "deleted_at" not in columns:
            op.add_column(
                "users",
                sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            )
    else:
        # In offline mode, emit SQL unconditionally (for review)
        op.add_column(
            "users",
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    # Add deletion_scheduled_for column (if not already present)
    if not _is_offline(bind):
        inspector = sa.inspect(bind)
        columns = [c["name"] for c in inspector.get_columns("users")]
        if "deletion_scheduled_for" not in columns:
            op.add_column(
                "users",
                sa.Column("deletion_scheduled_for", sa.DateTime(timezone=True), nullable=True),
            )
    else:
        # In offline mode, emit SQL unconditionally (for review)
        op.add_column(
            "users",
            sa.Column("deletion_scheduled_for", sa.DateTime(timezone=True), nullable=True),
        )

    # Create indexes for soft-delete queries
    op.create_index("idx_users_deleted_at", "users", ["deleted_at"])
    op.create_index("idx_users_deletion_scheduled_for", "users", ["deletion_scheduled_for"])


def downgrade() -> None:
    """Downgrade schema - remove soft-delete columns from users table."""
    op.drop_index("idx_users_deletion_scheduled_for", table_name="users")
    op.drop_index("idx_users_deleted_at", table_name="users")
    op.drop_column("users", "deletion_scheduled_for")
    op.drop_column("users", "deleted_at")
