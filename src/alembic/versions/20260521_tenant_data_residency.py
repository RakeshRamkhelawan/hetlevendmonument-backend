"""add data_residency and twin_hard_delete_max_hours to tenants

Revision ID: 20260521_tenant_data_residency
Revises: db72aec98edc
Create Date: 2026-05-21 07:55:00.000000

"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260521_tenant_data_residency"
down_revision: str | None = "db72aec98edc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "data_residency",
            sa.String(16),
            nullable=False,
            server_default="global",
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "twin_hard_delete_max_hours",
            sa.Integer,
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tenants", "twin_hard_delete_max_hours")
    op.drop_column("tenants", "data_residency")
