"""create digital twin tables

Revision ID: 20260519_create_digital_twin_tables
Revises: d4df5fd3e3ae
Create Date: 2026-05-19

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260519_create_digital_twin_tables"
down_revision: str | Sequence[str] | None = "20260518_add_is_superuser_server_default"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create digital twin tables."""
    # Table 1: user_behavior_observations
    op.create_table(
        "user_behavior_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("human_user_id", sa.String(255), nullable=False),
        sa.Column("session_id", sa.String(255), nullable=False),
        sa.Column("behavior_type", sa.String(100), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("outcome_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_twin_obs_user_time", "user_behavior_observations", ["human_user_id", "created_at"]
    )
    op.create_index(
        "idx_twin_obs_session", "user_behavior_observations", ["session_id", "created_at"]
    )
    op.create_index(
        "idx_twin_obs_tenant_behavior",
        "user_behavior_observations",
        ["tenant_id", "behavior_type"],
    )
    op.create_index("idx_twin_obs_expires", "user_behavior_observations", ["expires_at"])
    op.create_index("ix_user_behavior_observations_id", "user_behavior_observations", ["id"])
    op.create_index(
        "ix_user_behavior_observations_tenant_id",
        "user_behavior_observations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_user_behavior_observations_human_user_id",
        "user_behavior_observations",
        ["human_user_id"],
    )
    op.create_index(
        "ix_user_behavior_observations_session_id",
        "user_behavior_observations",
        ["session_id"],
    )
    op.create_index(
        "ix_user_behavior_observations_behavior_type",
        "user_behavior_observations",
        ["behavior_type"],
    )
    op.create_index(
        "ix_user_behavior_observations_created_at",
        "user_behavior_observations",
        ["created_at"],
    )

    # Table 2: user_cognitive_profiles
    op.create_table(
        "user_cognitive_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("human_user_id", sa.String(255), nullable=False),
        sa.Column("coding_style", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("work_patterns", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("blind_spots", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "optimal_help_style",
            sa.String(50),
            nullable=False,
            server_default="direct_code",
        ),
        sa.Column("confidence_level", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "preferred_agents",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "preferred_departments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "human_user_id", name="uq_twin_profile_tenant_user"),
    )
    op.create_index("idx_twin_profile_user", "user_cognitive_profiles", ["human_user_id"])
    op.create_index("ix_user_cognitive_profiles_id", "user_cognitive_profiles", ["id"])
    op.create_index(
        "ix_user_cognitive_profiles_tenant_id", "user_cognitive_profiles", ["tenant_id"]
    )
    op.create_index(
        "ix_user_cognitive_profiles_human_user_id",
        "user_cognitive_profiles",
        ["human_user_id"],
    )

    # Table 3: user_twin_consent
    op.create_table(
        "user_twin_consent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("human_user_id", sa.String(255), nullable=False),
        sa.Column("consent_given", sa.Boolean(), nullable=False, server_default="TRUE"),
        sa.Column("consent_version", sa.String(20), nullable=False, server_default="'1.0'"),
        sa.Column(
            "hard_delete_requested",
            sa.Boolean(),
            nullable=False,
            server_default="FALSE",
        ),
        sa.Column("hard_delete_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "human_user_id", name="uq_twin_consent_tenant_user"),
    )
    op.create_index("ix_user_twin_consent_id", "user_twin_consent", ["id"])
    op.create_index("ix_user_twin_consent_tenant_id", "user_twin_consent", ["tenant_id"])
    op.create_index("ix_user_twin_consent_human_user_id", "user_twin_consent", ["human_user_id"])

    # Table 4: focus_builder_accepted_workflows
    op.create_table(
        "focus_builder_accepted_workflows",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("template_id", sa.String(64), nullable=True),
        sa.Column(
            "nodes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column(
            "edges", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column("intake_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_fb_accepted_user_tenant",
        "focus_builder_accepted_workflows",
        ["user_id", "tenant_id", "created_at"],
    )


def downgrade() -> None:
    """Drop digital twin tables in reverse order."""
    op.drop_index("idx_fb_accepted_user_tenant", table_name="focus_builder_accepted_workflows")
    op.drop_table("focus_builder_accepted_workflows")

    op.drop_index("ix_user_twin_consent_human_user_id", table_name="user_twin_consent")
    op.drop_index("ix_user_twin_consent_tenant_id", table_name="user_twin_consent")
    op.drop_index("ix_user_twin_consent_id", table_name="user_twin_consent")
    op.drop_table("user_twin_consent")

    op.drop_index("ix_user_cognitive_profiles_human_user_id", table_name="user_cognitive_profiles")
    op.drop_index("ix_user_cognitive_profiles_tenant_id", table_name="user_cognitive_profiles")
    op.drop_index("ix_user_cognitive_profiles_id", table_name="user_cognitive_profiles")
    op.drop_index("idx_twin_profile_user", table_name="user_cognitive_profiles")
    op.drop_table("user_cognitive_profiles")

    op.drop_index(
        "ix_user_behavior_observations_created_at", table_name="user_behavior_observations"
    )
    op.drop_index(
        "ix_user_behavior_observations_behavior_type", table_name="user_behavior_observations"
    )
    op.drop_index(
        "ix_user_behavior_observations_session_id", table_name="user_behavior_observations"
    )
    op.drop_index(
        "ix_user_behavior_observations_human_user_id", table_name="user_behavior_observations"
    )
    op.drop_index(
        "ix_user_behavior_observations_tenant_id", table_name="user_behavior_observations"
    )
    op.drop_index("ix_user_behavior_observations_id", table_name="user_behavior_observations")
    op.drop_index("idx_twin_obs_expires", table_name="user_behavior_observations")
    op.drop_index("idx_twin_obs_tenant_behavior", table_name="user_behavior_observations")
    op.drop_index("idx_twin_obs_session", table_name="user_behavior_observations")
    op.drop_index("idx_twin_obs_user_time", table_name="user_behavior_observations")
    op.drop_table("user_behavior_observations")
