"""Align user profile columns with the current RBAC user model.

Revision ID: 20260407_user_profile_align
Revises: 20260407_auth_schema_alignment
Create Date: 2026-04-07
"""

from typing import Union
from collections.abc import Sequence

from alembic import op


revision: str = "20260407_user_profile_align"
down_revision: str | None = "20260407_auth_schema_alignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing user profile columns used by auth and security middleware."""
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS preferred_locale VARCHAR(10)
        """
    )
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS preferred_timezone VARCHAR(50)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_stripe_customer_id
        ON users (stripe_customer_id)
        WHERE stripe_customer_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Remove the user profile alignment columns."""
    op.execute("DROP INDEX IF EXISTS ix_users_stripe_customer_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_timezone")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS preferred_locale")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS stripe_customer_id")