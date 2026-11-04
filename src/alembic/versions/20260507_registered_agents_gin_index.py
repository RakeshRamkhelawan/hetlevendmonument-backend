"""Add GIN index on registered_agents.capabilities for fast JSONB queries.

Revision ID: 20260507_gin_index
Revises: 20260507_registered_agent_per_tenant_unique
Create Date: 2026-05-07
"""

from __future__ import annotations

import alembic.context
import sqlalchemy as sa
from alembic import op

revision = "20260507_gin_index"
down_revision = "20260507_registered_agent_per_tenant_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if alembic.context.is_offline_mode():
        # Offline dry-run: emit SQL unconditionally for review
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_registered_agents_capabilities_gin "
                "ON registered_agents USING gin ((capabilities::jsonb) jsonb_path_ops)"
            )
        )
        op.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS ix_registered_agents_tenant_id_btree "
                "ON registered_agents (tenant_id)"
            )
        )
        return

    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_registered_agents_capabilities_gin "
            "ON registered_agents USING gin ((capabilities::jsonb) jsonb_path_ops)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_registered_agents_tenant_id_btree "
            "ON registered_agents (tenant_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_registered_agents_capabilities_gin"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_registered_agents_tenant_id_btree"))
