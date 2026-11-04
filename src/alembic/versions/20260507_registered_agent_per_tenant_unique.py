"""registered_agents: per-tenant unique constraint on (agent_id, tenant_id)

Revision ID: 20260507_registered_agent_per_tenant_unique
Revises: 20260427_create_conversations
Create Date: 2026-05-07
"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260507_registered_agent_per_tenant_unique"
down_revision: str | Sequence[str] | None = "20260427_create_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the existing global unique constraint on agent_id (if it exists).
    # Using raw SQL with IF EXISTS so it works when the constraint was never
    # created (e.g. databases bootstrapped from a schema where the table was
    # created without it).
    op.execute(
        sa.text(
            "ALTER TABLE registered_agents DROP CONSTRAINT IF EXISTS registered_agents_agent_id_key"
        )
    )
    # Also drop the per-tenant constraint if it already exists (idempotent).
    op.execute(
        sa.text(
            "ALTER TABLE registered_agents DROP CONSTRAINT IF EXISTS uq_registered_agent_per_tenant"
        )
    )
    # Create per-tenant unique constraint so each tenant can have its own agent_id
    op.create_unique_constraint(
        "uq_registered_agent_per_tenant", "registered_agents", ["agent_id", "tenant_id"]
    )
    # Add index on agent_id alone for fast cross-tenant lookups
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS idx_registered_agent_id ON registered_agents (agent_id)"))


def downgrade() -> None:
    op.drop_index("idx_registered_agent_id", table_name="registered_agents")
    op.drop_constraint("uq_registered_agent_per_tenant", "registered_agents", type_="unique")
    op.create_unique_constraint("registered_agents_agent_id_key", "registered_agents", ["agent_id"])
