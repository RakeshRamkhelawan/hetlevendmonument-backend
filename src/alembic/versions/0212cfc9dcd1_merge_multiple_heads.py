"""merge_multiple_heads

Revision ID: 0212cfc9dcd1
Revises: 20260506_add_department_function_fields, 20260507_gin_index, 20260509_140000
Create Date: 2026-05-10 09:46:28.282670

"""
from typing import Union
from collections.abc import Sequence



# revision identifiers, used by Alembic.
revision: str = '0212cfc9dcd1'
down_revision: str | Sequence[str] | None = ('20260506_add_department_function_fields', '20260507_gin_index', '20260509_140000')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
