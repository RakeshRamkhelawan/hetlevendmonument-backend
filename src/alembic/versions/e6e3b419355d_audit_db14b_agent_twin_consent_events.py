"""audit_db14b_agent_twin_consent_events

Revision ID: e6e3b419355d
Revises: 20260627_critique_hourly_stats_mv
Create Date: 2026-07-01 16:24:46.497502

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6e3b419355d"
down_revision: Union[str, Sequence[str], None] = "20260627_critique_hourly_stats_mv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Maak agent_twin_consent_events tabel aan (ADR-026, ADR-005)."""
    op.create_table(
        "agent_twin_consent_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("observe", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_atce_tenant_agent",
        "agent_twin_consent_events",
        ["tenant_id", "agent_id"],
    )
    op.create_index(
        "ix_atce_agent_id",
        "agent_twin_consent_events",
        ["agent_id"],
    )


def downgrade() -> None:
    """Verwijder agent_twin_consent_events tabel."""
    op.drop_index("ix_atce_agent_id", table_name="agent_twin_consent_events")
    op.drop_index("ix_atce_tenant_agent", table_name="agent_twin_consent_events")
    op.drop_table("agent_twin_consent_events")
