"""Futureproof baseline - Clean schema for Paperclip Pipeline

Revision ID: 20260330_futureproof_baseline
Revises:
Create Date: 2026-03-30 12:00:00.000000

This is a futureproof baseline migration that creates all tables in the correct order
with proper foreign key constraints and without the issues present in previous migrations.

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260330_futureproof_baseline"
down_revision: str | Sequence[str] | None = "20260311_006c_contract_add_fk_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create all tables in dependency order."""

    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    # CREATE EXTENSION is PostgreSQL-only -- skip on SQLite (used in CI in-memory DB)
    if conn.dialect.name == "postgresql":
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
        op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # Skip Paperclip tables on SQLite -- they use PostgreSQL-specific types (ARRAY, JSONB, UUID)
    # In offline mode (CI dry-run), this whole section is skipped silently.
    # In production (PostgreSQL), these tables are created.
    if is_sqlite:
        op.execute(
            sa.text(
                "-- Skipped on SQLite: domain_packs, pack_activations, pack_health_metrics, "
                "experiments, experiment_participants, ml_training_data, ml_models, "
                "pack_usage_aggregates (PostgreSQL-specific types)"
            )
        )
    else:
        # =============================================================================
        # PAPERCLIP PIPELINE TABLES
        # companies, departments, goals are created by 20260311_001-006c migrations
        # =============================================================================

        # Domain Packs
        op.create_table(
            "domain_packs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column(
                "tenant_id",
                sa.Integer(),
                sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("version", sa.Integer(), default=1),
            sa.Column("description", sa.String(length=2000)),
            sa.Column("category", sa.String(length=100)),
            sa.Column("capabilities", postgresql.ARRAY(sa.String()), default=[]),
            sa.Column("input_contracts", postgresql.JSONB(), default={}),
            sa.Column("output_contracts", postgresql.JSONB(), default={}),
            sa.Column("is_active", sa.Boolean(), default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
            ),
        )
        op.create_index("idx_domain_pack_tenant", "domain_packs", ["tenant_id"])
        op.create_index(
            "idx_domain_pack_tenant_name",
            "domain_packs",
            ["tenant_id", "name", "version"],
            unique=True,
        )

        # Pack Activations
        op.create_table(
            "pack_activations",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "department_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("departments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "pack_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("domain_packs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("status", sa.String(length=50), default="active"),
            sa.Column("activation_score", sa.Float()),
            sa.Column("health_score", sa.Float()),
            sa.Column("last_activity_at", sa.DateTime(timezone=True)),
            sa.Column("grace_period_end", sa.DateTime(timezone=True)),
            sa.Column("activated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("deactivated_at", sa.DateTime(timezone=True)),
        )
        op.create_index("idx_pack_activation_company", "pack_activations", ["company_id"])
        op.create_index("idx_pack_activation_department", "pack_activations", ["department_id"])
        op.create_index("idx_pack_activation_pack", "pack_activations", ["pack_id"])
        op.create_index(
            "idx_pack_activation_status",
            "pack_activations",
            ["company_id", "department_id", "status"],
        )

        # pack_activation_audit_logs is created by 20260311_005_create_pack_activation_audit_log

        # Pack Health Metrics
        op.create_table(
            "pack_health_metrics",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column(
                "pack_activation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("pack_activations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("usage_count", sa.Integer(), default=0),
            sa.Column("user_engagement_score", sa.Float()),
            sa.Column("error_count", sa.Integer(), default=0),
            sa.Column("avg_response_time_ms", sa.Float()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "idx_health_metrics_activation", "pack_health_metrics", ["pack_activation_id"]
        )
        op.create_index("idx_health_metrics_date", "pack_health_metrics", ["date"])

        # Experiments
        op.create_table(
            "experiments",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text()),
            sa.Column("hypothesis", sa.Text()),
            sa.Column("status", sa.String(length=50), default="draft"),
            sa.Column("traffic_split", sa.Float(), default=0.5),
            sa.Column("metrics", postgresql.JSONB(), default=[]),
            sa.Column("target_segments", postgresql.JSONB(), default={}),
            sa.Column("start_date", sa.Date()),
            sa.Column("end_date", sa.Date()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
            ),
        )

        # Experiment Participants
        op.create_table(
            "experiment_participants",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column(
                "experiment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("experiments.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("variant", sa.String(length=50), nullable=False),
            sa.Column("exposed_at", sa.DateTime(timezone=True)),
            sa.Column("converted_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "idx_exp_participant_experiment", "experiment_participants", ["experiment_id"]
        )
        op.create_index("idx_exp_participant_company", "experiment_participants", ["company_id"])
        op.create_index(
            "idx_exp_participant_unique",
            "experiment_participants",
            ["experiment_id", "company_id"],
            unique=True,
        )

        # ML Training Data
        op.create_table(
            "ml_training_data",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column(
                "company_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("companies.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "pack_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("domain_packs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("company_features", postgresql.JSONB(), nullable=False),
            sa.Column("pack_features", postgresql.JSONB(), nullable=False),
            sa.Column("activated", sa.Boolean(), nullable=False),
            sa.Column("activation_date", sa.Date()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("idx_ml_training_company", "ml_training_data", ["company_id"])
        op.create_index("idx_ml_training_pack", "ml_training_data", ["pack_id"])

        # ML Models
        op.create_table(
            "ml_models",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("model_type", sa.String(length=100), nullable=False),
            sa.Column("version", sa.String(length=50), nullable=False),
            sa.Column("file_path", sa.String(length=500)),
            sa.Column("accuracy", sa.Float()),
            sa.Column("precision", sa.Float()),
            sa.Column("recall", sa.Float()),
            sa.Column("f1_score", sa.Float()),
            sa.Column("sample_count", sa.Integer()),
            sa.Column("is_active", sa.Boolean(), default=False),
            sa.Column("trained_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("idx_ml_model_active", "ml_models", ["model_type", "is_active"])

        # Pack Usage Aggregates (for cross-company analytics)
        op.create_table(
            "pack_usage_aggregates",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("uuid_generate_v4()"),
            ),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("sector", sa.String(length=100), nullable=False),
            sa.Column("company_size", sa.String(length=50), nullable=False),
            sa.Column(
                "pack_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("domain_packs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("total_activations", sa.Integer(), default=0),
            sa.Column("active_companies", sa.Integer(), default=0),
            sa.Column("avg_health_score", sa.Float()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
            ),
        )
        op.create_index("idx_usage_agg_date", "pack_usage_aggregates", ["date"])
        op.create_index(
            "idx_usage_agg_segment", "pack_usage_aggregates", ["sector", "company_size"]
        )
        op.create_index(
            "idx_usage_agg_unique",
            "pack_usage_aggregates",
            ["date", "sector", "company_size", "pack_id"],
            unique=True,
        )

    # =============================================================================
    # AGENT TABLES
    # Uses IF NOT EXISTS so this is safe to run on databases that already have
    # these tables from archived historical migrations (e.g. production).
    # NOTE: department_id column is NOT included here -- it is added by the
    # 20260404_add_agent_department_fk migration that follows this baseline.
    # NOTE: Agent tables use PostgreSQL syntax (SERIAL, TIMESTAMPTZ) -- skip on SQLite.
    # =============================================================================

    if is_sqlite:
        op.execute(
            sa.text("-- Skipped on SQLite: agents, registered_agents (PostgreSQL-specific types)")
        )
    else:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                id          SERIAL PRIMARY KEY,
                name        VARCHAR(100) NOT NULL,
                agent_type  VARCHAR(50) NOT NULL,
                tenant_id   INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        op.execute("CREATE INDEX IF NOT EXISTS idx_agents_tenant ON agents(tenant_id)")

        op.execute(
            """
            CREATE TABLE IF NOT EXISTS registered_agents (
                id              SERIAL PRIMARY KEY,
                agent_id        VARCHAR(255) NOT NULL UNIQUE,
                name            VARCHAR(255),
                description     VARCHAR(1000),
                address         VARCHAR(500) NOT NULL,
                capabilities    JSONB,
                last_heartbeat  TIMESTAMPTZ,
                tenant_id       INTEGER NOT NULL REFERENCES tenants(id),
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_heartbeat ON registered_agents(last_heartbeat)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_status ON registered_agents(last_heartbeat, created_at)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_tenant ON registered_agents(tenant_id, agent_id)"
        )


def downgrade() -> None:
    """Drop all tables in reverse order.

    Only drops tables created by THIS migration.
    tenants, companies, departments, goals, pack_activation_audit_logs
    are owned by their respective migrations (000, 001, 005).
    """

    # Drop Paperclip Pipeline tables (owned by this migration)
    op.drop_table("pack_usage_aggregates")
    op.drop_table("ml_models")
    op.drop_table("ml_training_data")
    op.drop_table("experiment_participants")
    op.drop_table("experiments")
    op.drop_table("pack_health_metrics")
    op.drop_table("pack_activations")
    op.drop_table("domain_packs")

    # Drop Agent tables (created with IF NOT EXISTS raw SQL)
    op.execute("DROP TABLE IF EXISTS registered_agents")
    op.execute("DROP TABLE IF EXISTS agents")

    # Drop Core tables (owned by this migration)
