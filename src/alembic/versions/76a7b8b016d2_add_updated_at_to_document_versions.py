"""add_updated_at_to_document_versions

Revision ID: 76a7b8b016d2
Revises: 20260528c
Create Date: 2026-05-29 00:23:07.500739

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '76a7b8b016d2'
down_revision: str | Sequence[str] | None = '20260528c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add updated_at column to document_versions for consistency with other models."""
    op.add_column(
        'document_versions',
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('clock_timestamp()'),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop updated_at column from document_versions."""
    op.drop_column('document_versions', 'updated_at')
