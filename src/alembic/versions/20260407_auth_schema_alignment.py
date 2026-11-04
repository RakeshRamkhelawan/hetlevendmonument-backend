"""Align auth-related schema with current RBAC and lockout models.

Revision ID: 20260407_auth_schema_alignment
Revises: 20260404_add_agent_department_fk
Create Date: 2026-04-07

This migration is intentionally idempotent for drifted local/dev databases.
It adds auth fields that are used by the current code but were missing from the
futureproof baseline:

- users.last_login
- roles.description
- account_lockouts table
"""

from typing import Union
from collections.abc import Sequence


from alembic import op


revision: str = "20260407_auth_schema_alignment"
down_revision: str | None = "20260404_add_agent_department_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add missing auth schema objects needed by the login flow."""
    op.execute(
        """
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITH TIME ZONE
        """
    )

    op.execute(
        """
        ALTER TABLE roles
        ADD COLUMN IF NOT EXISTS description VARCHAR(200)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS account_lockouts (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMP WITH TIME ZONE,
            last_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            ip_address VARCHAR(45),
            user_agent VARCHAR(255)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_lockout_user_ip
        ON account_lockouts (user_id, ip_address)
        """
    )


def downgrade() -> None:
    """Remove auth schema alignment changes."""
    op.execute("DROP INDEX IF EXISTS idx_lockout_user_ip")
    op.execute("DROP TABLE IF EXISTS account_lockouts")
    op.execute("ALTER TABLE roles DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_login")