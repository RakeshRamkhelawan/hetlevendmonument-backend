"""add learning OODA tables

Revision ID: 20260515_add_learning_ooda_tables
Revises: 0212cfc9dcd1
Create Date: 2026-05-15 00:00:00.000000

Creates tables for learning patterns, adaptation rules, and learning insights.
Part of T2-B: OODA/Learning persistence for adaptive learning system.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260515_add_learning_ooda_tables"
down_revision: str | Sequence[str] | None = "0212cfc9dcd1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_offline(bind) -> bool:
    """Check if running in offline mode (for alembic upgrade head --sql)."""
    return isinstance(bind, sa.engine.mock.MockConnection)


def upgrade() -> None:
    """Upgrade schema - create learning tables."""
    bind = op.get_bind()

    # Create learning_patterns table
    if not _is_offline(bind):
        inspector = sa.inspect(bind)
        if not inspector.has_table("learning_patterns"):
            op.create_table(
                "learning_patterns",
                sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
                sa.Column("tenant_id", sa.String(128), nullable=False),
                sa.Column("pattern_id", sa.String(255), nullable=False, unique=True),
                sa.Column("pattern_type", sa.String(100), nullable=False),
                sa.Column("trigger_conditions", sa.JSON(), nullable=False),
                sa.Column("learned_behavior", sa.JSON(), nullable=False),
                sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="0"),
                sa.Column("success_rate", sa.Float(), nullable=False, server_default="0.0"),
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
                sa.Column("source", sa.String(100), nullable=True),
                sa.Column("agent_id", sa.String(255), nullable=True),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.UniqueConstraint("pattern_id"),
            )
            op.create_index("ix_learning_patterns_tenant", "learning_patterns", ["tenant_id"])
            op.create_index(
                "ix_learning_patterns_type", "learning_patterns", ["pattern_type", "is_active"]
            )
            op.create_index(
                "ix_learning_patterns_agent", "learning_patterns", ["tenant_id", "agent_id"]
            )

    # NOTE: adaptation_rules table is created by a45f3cd4bfb3_create_adaptation_rules_table.py
    # This migration focuses on learning_patterns and learning_insights for the OODA/Learning MVP.

    # Create learning_insights table
    if not _is_offline(bind):
        inspector = sa.inspect(bind)
        if not inspector.has_table("learning_insights"):
            op.create_table(
                "learning_insights",
                sa.Column("id", sa.String(128), nullable=False),
                sa.Column("insight_id", sa.String(128), nullable=False, unique=True),
                sa.Column("tenant_id", sa.String(128), nullable=False),
                sa.Column(
                    "conversation_id", sa.String(255), nullable=False, server_default="system"
                ),
                sa.Column("insight_type", sa.String(100), nullable=False),
                sa.Column("title", sa.String(500), nullable=True),
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("category", sa.String(100), nullable=True),
                sa.Column("rating", sa.Integer(), nullable=True),
                sa.Column("comment", sa.Text(), nullable=True),
                sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
                sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0.5"),
                sa.Column("impact_assessment", sa.JSON(), nullable=True),
                sa.Column("recommended_actions", sa.JSON(), nullable=True),
                sa.Column("context", sa.JSON(), nullable=True),
                sa.Column("evidence", sa.JSON(), nullable=True),
                sa.Column("processed", sa.Boolean(), nullable=True, server_default="false"),
                sa.Column(
                    "adaptation_applied", sa.Boolean(), nullable=True, server_default="false"
                ),
                sa.Column("is_actionable", sa.Boolean(), nullable=False, server_default="true"),
                sa.Column("agent_id", sa.String(255), nullable=True),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                ),
                sa.PrimaryKeyConstraint("id"),
                sa.UniqueConstraint("insight_id"),
            )
            op.create_index("ix_learning_insights_tenant", "learning_insights", ["tenant_id"])
            op.create_index(
                "ix_learning_insights_type", "learning_insights", ["insight_type", "is_actionable"]
            )


def downgrade() -> None:
    """Downgrade schema - drop learning tables."""
    op.drop_table("learning_insights")
    op.drop_table("learning_patterns")
