"""add execution fields to council_decisions

Revision ID: 20260525b
Revises: 96e1e394d034
Create Date: 2026-05-25 11:30:00.000000

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260525b'
down_revision: str | Sequence[str] | None = '96e1e394d034'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("council_decisions", sa.Column("result_hash", sa.String(length=64), nullable=True))
    op.add_column("council_decisions", sa.Column("execution_status", sa.String(length=16), nullable=True))
    
    # Backfill
    op.execute("UPDATE council_decisions SET execution_status = 'pending'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("council_decisions", "execution_status")
    op.drop_column("council_decisions", "result_hash")
