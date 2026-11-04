"""fix_gin_index_normalize_underscores

Revision ID: 93475c4a00a0
Revises: b9f4c2e1a053
Create Date: 2026-05-28 23:25:56.875398

"""
from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '93475c4a00a0'
down_revision: str | Sequence[str] | None = 'b9f4c2e1a053'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Recreate GIN index with underscore normalization for fulltext search."""
    op.execute("DROP INDEX IF EXISTS ix_documents_filename_gin")
    op.execute(
        "CREATE INDEX ix_documents_filename_gin ON documents "
        "USING gin(to_tsvector('english', replace(filename, '_', ' ')))"
    )


def downgrade() -> None:
    """Restore original GIN index without normalization."""
    op.execute("DROP INDEX IF EXISTS ix_documents_filename_gin")
    op.execute(
        "CREATE INDEX ix_documents_filename_gin ON documents "
        "USING gin(to_tsvector('english', filename))"
    )
