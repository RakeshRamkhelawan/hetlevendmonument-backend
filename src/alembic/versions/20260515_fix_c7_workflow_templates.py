"""fix c7_workflow_templates schema

Revision ID: 20260515_fix_c7_workflow_templates
Revises: 20260515_add_learning_ooda_tables
Create Date: 2026-05-15 00:00:01.000000

Creates or fixes the c7_workflow_templates table for workflow template management.
Part of T2-C: Workflow template persistence for template marketplace.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_fix_c7_workflow_templates"
down_revision: str | Sequence[str] | None = "20260515_add_learning_ooda_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind) -> bool:
    """Check if running in offline mode (for alembic upgrade head --sql)."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    """Upgrade schema - create c7_workflow_templates table."""
    bind = op.get_bind()

    if not _is_offline(bind):
        inspector = sa.inspect(bind)
        if not inspector.has_table("c7_workflow_templates"):
            op.create_table(
                "c7_workflow_templates",
                sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
                sa.Column("template_id", sa.String(100), nullable=False, unique=True),
                sa.Column("name", sa.String(200), nullable=False),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("category", sa.String(100), nullable=True),
                sa.Column("spec_json", sa.JSON(), nullable=False),
                sa.Column("author", sa.String(100), nullable=True),
                sa.Column("is_public", sa.Boolean(), nullable=False, server_default="false"),
                sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
                sa.PrimaryKeyConstraint("id"),
                sa.UniqueConstraint("template_id"),
            )
            op.create_index(
                "idx_c7_template_category", "c7_workflow_templates", ["category", "usage_count"]
            )
            op.create_index("idx_c7_template_id", "c7_workflow_templates", ["template_id"])


def downgrade() -> None:
    """Downgrade schema - drop c7_workflow_templates table."""
    op.drop_table("c7_workflow_templates")
