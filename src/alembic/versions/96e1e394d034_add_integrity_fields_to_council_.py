"""add integrity fields to council_decisions

Revision ID: 96e1e394d034
Revises: 20260525a
Create Date: 2026-05-25 09:20:08.977423

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '96e1e394d034'
down_revision: str | Sequence[str] | None = '20260525a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("council_decisions", sa.Column("trigger", sa.String(length=32), nullable=True))
    op.add_column("council_decisions", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("council_decisions", sa.Column("message", sa.Text(), nullable=True))
    op.add_column("council_decisions", sa.Column("officer_verdicts_hash", sa.String(length=64), nullable=True))
    
    # Backfill with defaults for existing records
    op.execute("UPDATE council_decisions SET trigger = 'user_request', confidence = 1.0, message = '', officer_verdicts_hash = ''")
    
    # Optional: make non-nullable after backfill if needed
    # op.alter_column("council_decisions", "trigger", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("council_decisions", "officer_verdicts_hash")
    op.drop_column("council_decisions", "message")
    op.drop_column("council_decisions", "confidence")
    op.drop_column("council_decisions", "trigger")
