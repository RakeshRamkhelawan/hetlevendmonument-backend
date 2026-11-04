"""add twin_suggestion_log and tenant_llm_budget tables

Revision ID: 20260521c_twin_suggestion_log_and_budget
Revises: 20260521_twin_consent_categories
Create Date: 2026-05-21 10:00:00.000000

"""

from typing import Union
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260521c_twin_suggestion_log_and_budget"
down_revision: str | None = "20260521_twin_consent_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # twin_suggestion_log: per-suggestion cost tracking (7-year retention)
    op.create_table(
        "twin_suggestion_log",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("provider_name", sa.String(50), nullable=False),
        sa.Column("suggestion_text", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_eur", sa.Numeric(precision=10, scale=6), nullable=False, server_default="0"),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("was_useful", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_twin_suggestion_log_tenant_user",
        "twin_suggestion_log",
        ["tenant_id", "user_id"],
    )
    op.create_index(
        "idx_twin_suggestion_log_created",
        "twin_suggestion_log",
        ["created_at"],
    )
    op.create_index(
        "idx_twin_suggestion_log_expires",
        "twin_suggestion_log",
        ["expires_at"],
    )

    # tenant_llm_budget: per-tenant monthly budget caps
    op.create_table(
        "tenant_llm_budget",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.String(7), nullable=False),  # YYYY-MM
        sa.Column(
            "budget_eur_soft",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="10.00",
        ),
        sa.Column(
            "budget_eur_hard",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="50.00",
        ),
        sa.Column(
            "spent_eur",
            sa.Numeric(precision=10, scale=6),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "month", name="uq_tenant_llm_budget_month"),
    )
    op.create_index(
        "idx_tenant_llm_budget_tenant",
        "tenant_llm_budget",
        ["tenant_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_tenant_llm_budget_tenant", table_name="tenant_llm_budget")
    op.drop_table("tenant_llm_budget")
    op.drop_index("idx_twin_suggestion_log_expires", table_name="twin_suggestion_log")
    op.drop_index("idx_twin_suggestion_log_created", table_name="twin_suggestion_log")
    op.drop_index("idx_twin_suggestion_log_tenant_user", table_name="twin_suggestion_log")
    op.drop_table("twin_suggestion_log")
