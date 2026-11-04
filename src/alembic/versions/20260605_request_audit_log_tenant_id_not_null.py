"""request_audit_log_tenant_id_not_null

Revision ID: 20260605a
Revises: 3ee55ea8e623
Create Date: 2026-06-05 00:30:00.000000

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260605a'
down_revision: str | Sequence[str] | None = '3ee55ea8e623'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind) -> bool:
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    """Upgrade schema: make tenant_id NOT NULL with fallback."""
    bind = op.get_bind()
    if not _is_offline(bind):
        # Step 1: Update existing NULL rows to a deterministic fallback
        op.execute(
            sa.text("UPDATE request_audit_logs SET tenant_id = '0' WHERE tenant_id IS NULL")
        )

    # Step 2: Alter column to NOT NULL
    op.alter_column(
        "request_audit_logs",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema: make tenant_id nullable again."""
    op.alter_column(
        "request_audit_logs",
        "tenant_id",
        existing_type=sa.String(length=50),
        nullable=True,
    )
