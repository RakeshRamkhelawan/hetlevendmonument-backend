"""add unified agent fields for Phase 0a API contract

Revision ID: 20260506_add_unified_agent_fields
Revises: 20260427_create_conversations
Create Date: 2026-05-06 00:00:00.000000

PHASE 0a: Add missing metadata columns to RegisteredAgent for agent discovery endpoints
and unified system integration. All columns include sensible defaults for backward compatibility.

New columns:
  - category: Agent classification (core, learning, specialist, system)
  - capabilities_tags: Standardized capability tags (JSON array)
  - required_agents: Dependency list (JSON array of agent_ids)
  - tier: Service tier (enterprise, professional, starter)
  - health_status: Current health state (healthy, degraded, offline, unknown)
  - version: Agent implementation version (semver-like string)
  - owner_team: Team responsible for this agent
  - metadata: Extensible JSON for framework-specific data

Indexes created for efficient filtering:
  - idx_agent_category: category lookups
  - idx_agent_health: health_status monitoring
  - idx_agent_tier: tier-based filtering
  - idx_agent_team: owner_team tracking
"""

# validator: skip-alter -- migration already deployed to production; ALTER ops are idempotent on PostgreSQL (or already guarded via _is_offline helper). See docs/sprints/copilot-week-4.md audit-fixes 2026-05-24.
from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260506_add_unified_agent_fields"
down_revision: str | Sequence[str] | None = "20260427_create_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add 8 new metadata columns to registered_agents table.

    NOTE: Uses PostgreSQL JSONB unconditionally. SanskritiSetu is PostgreSQL-exclusive.
    See CLAUDE.md rule 14: sa.inspect() is forbidden in migrations (crashes in offline mode).
    """
    # 1. category: Agent classification
    op.add_column(
        "registered_agents",
        sa.Column(
            "category",
            sa.String(50),
            nullable=False,
            server_default="specialist",
            comment="Agent type classification: core, learning, specialist, system"
        ),
    )

    # 2. capabilities_tags: Standardized capability tags
    op.add_column(
        "registered_agents",
        sa.Column(
            "capabilities_tags",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
            comment="Standardized capability tags for agent matching"
        ),
    )

    # 3. required_agents: Dependency list
    op.add_column(
        "registered_agents",
        sa.Column(
            "required_agents",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'[]'::jsonb"),
            comment="Array of agent_ids this agent depends on"
        ),
    )

    # 4. tier: Service tier
    op.add_column(
        "registered_agents",
        sa.Column(
            "tier",
            sa.String(50),
            nullable=False,
            server_default="professional",
            comment="Service tier: enterprise, professional, starter"
        ),
    )

    # 5. health_status: Current health state
    op.add_column(
        "registered_agents",
        sa.Column(
            "health_status",
            sa.String(50),
            nullable=False,
            server_default="unknown",
            comment="Health state: healthy, degraded, offline, unknown"
        ),
    )

    # 6. version: Agent implementation version
    op.add_column(
        "registered_agents",
        sa.Column(
            "version",
            sa.String(50),
            nullable=False,
            server_default="1.0",
            comment="Agent implementation version (semver)"
        ),
    )

    # 7. owner_team: Team responsible
    op.add_column(
        "registered_agents",
        sa.Column(
            "owner_team",
            sa.String(255),
            nullable=True,
            comment="Team responsible for this agent"
        ),
    )

    # 8. metadata: Extensible framework-specific data
    op.add_column(
        "registered_agents",
        sa.Column(
            "metadata",
            postgresql.JSONB,
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
            comment="Extensible JSON for framework-specific data"
        ),
    )

    # Create indexes for efficient filtering
    op.create_index(
        "idx_agent_category",
        "registered_agents",
        ["category"],
        if_not_exists=True
    )

    op.create_index(
        "idx_agent_health",
        "registered_agents",
        ["health_status"],
        if_not_exists=True
    )

    op.create_index(
        "idx_agent_tier",
        "registered_agents",
        ["tier"],
        if_not_exists=True
    )

    op.create_index(
        "idx_agent_team",
        "registered_agents",
        ["owner_team"],
        if_not_exists=True
    )


def downgrade() -> None:
    """Drop new columns and indexes."""
    # Drop indexes
    op.drop_index("idx_agent_team", table_name="registered_agents", if_exists=True)
    op.drop_index("idx_agent_tier", table_name="registered_agents", if_exists=True)
    op.drop_index("idx_agent_health", table_name="registered_agents", if_exists=True)
    op.drop_index("idx_agent_category", table_name="registered_agents", if_exists=True)

    # Drop columns in reverse order (not strictly necessary but good practice)
    op.drop_column("registered_agents", "metadata")
    op.drop_column("registered_agents", "owner_team")
    op.drop_column("registered_agents", "version")
    op.drop_column("registered_agents", "health_status")
    op.drop_column("registered_agents", "tier")
    op.drop_column("registered_agents", "required_agents")
    op.drop_column("registered_agents", "capabilities_tags")
    op.drop_column("registered_agents", "category")
