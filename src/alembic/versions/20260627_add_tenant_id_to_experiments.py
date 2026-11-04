"""add tenant_id to experiments (TI-003)

Revision ID: 20260627_add_tenant_id_experiments
Revises: 0092fdf7d725
Create Date: 2026-06-27

TI-003: A/B test experiments table lacked tenant_id, causing cross-tenant data exposure
in admin experiment endpoints. This migration adds the column and index.

The column is nullable to avoid breaking existing rows; a follow-up backfill
should set tenant_id for pre-existing records (tracked in SP-AUDIT-FIX-001 backlog).
"""

from alembic import op
import sqlalchemy as sa

revision = "20260627_add_tenant_id_experiments"
down_revision = "0092fdf7d725"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "experiments",
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_experiments_tenant_id",
        "experiments",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_experiments_tenant_id", table_name="experiments")
    op.drop_column("experiments", "tenant_id")
