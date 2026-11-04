"""Add agentic domain tables to live chain, tenant_id NOT NULL, RLS

Revision ID: 884d744f6aa9
Revises: e6e3b419355d
Create Date: 2026-07-02

DATA-001/002, DB-AUDIT-001/002 (AUDIT-ARCH-2026-07-02 Groep 4): the 9 agentic-domain
tables (prompt_templates, features, tool_definitions, prompt_metrics, user_personas,
agent_sessions, session_messages, prompt_experiments, prompt_experiment_variants) were
never part of the live Alembic chain. A stale migration exists under archive/
(2026_02_02_agentic_system_schema.py, 56358a9c33ea_add_prompt_experiment_tables.py) but
its schema predates significant model changes and no longer matches
src/domains/agentic/models.py (e.g. the archived "features" table has no "name" column
and uses JSONB where the model now uses portable JSON) -- confirmed via grep that this
archived migration was never referenced/run anywhere; tests bypass Alembic entirely via
Base.metadata.create_all() against the current models.

Per product owner (2026-07-02): pre-launch, no customers, no production data in these
tables to preserve. This migration creates the CURRENT model schema directly (source of
truth: src/domains/agentic/models.py) rather than replaying the stale archived DDL, with
tenant_id NOT NULL from creation (no backfill needed -- no existing data). RLS policies
follow the established <tbl>_tenant_isolation pattern (see
20260529b_harden_user_persona_preferences_tenant_integrity.py).

backend-patterns.md #9: NOOIT sa.inspect(op.get_bind()) in migraties -- crasht bij
offline dry-run (alembic upgrade head --sql, used by scripts/pre-deploy-check.sh).
Uses raw "CREATE TABLE IF NOT EXISTS" / "DROP TABLE IF EXISTS" SQL instead, matching
the established pattern in 20260404_gdpr_tables.py.

prompt_experiment_variants has no tenant_id column by design -- it is a child of
prompt_experiments (composite PK experiment_id+variant_id) and inherits isolation via
that FK. This is the first documented exception in the ORM auto-filter allowlist -- see
tests/architecture/test_orm_hook_guards_nullable_tenant_id.py (DB-AUDIT-003).
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "884d744f6aa9"
down_revision: Union[str, None] = "e6e3b419355d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::integer"

# Tables with a tenant_id column -- RLS applies. prompt_experiment_variants is
# deliberately excluded (no tenant_id, isolated via FK to prompt_experiments).
_TENANT_SCOPED_TABLES = [
    "prompt_templates",
    "features",
    "tool_definitions",
    "prompt_metrics",
    "user_personas",
    "agent_sessions",
    "session_messages",
    "prompt_experiments",
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            version VARCHAR(20) NOT NULL,
            system_prompt TEXT NOT NULL,
            context_template TEXT,
            output_format VARCHAR(50),
            supported_locales JSON,
            localized_variants JSON,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now(),
            CONSTRAINT uq_prompt_template_version UNIQUE (name, version, tenant_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prompt_templates_tenant_status "
        "ON prompt_templates (tenant_id, status)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS features (
            id VARCHAR(100) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            icon VARCHAR(100),
            color VARCHAR(7),
            keywords JSON,
            example_queries JSON,
            capabilities JSON,
            intent_keywords JSON,
            route_patterns JSON,
            domain_context VARCHAR(100),
            prompt_template_id INTEGER REFERENCES prompt_templates(id) ON DELETE SET NULL,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_features_tenant_active ON features (tenant_id, is_active)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_features_category ON features (category)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tool_definitions (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL UNIQUE,
            display_name VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            category VARCHAR(50) NOT NULL,
            function_schema JSON NOT NULL,
            implementation_type VARCHAR(50) NOT NULL DEFAULT 'internal',
            implementation_config JSON,
            required_permissions JSON,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_definitions_tenant_id ON tool_definitions (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_definitions_category ON tool_definitions (category)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tool_definitions_active ON tool_definitions (is_active)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_metrics (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            template_id INTEGER NOT NULL REFERENCES prompt_templates(id) ON DELETE CASCADE,
            session_id VARCHAR(100) NOT NULL,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            latency_ms INTEGER,
            token_count INTEGER,
            task_completed BOOLEAN,
            user_feedback INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prompt_metrics_tenant_id ON prompt_metrics (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prompt_metrics_created_at ON prompt_metrics (created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_personas (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            persona_type VARCHAR(50),
            expertise_level INTEGER NOT NULL DEFAULT 5,
            prefers_structured_output BOOLEAN NOT NULL DEFAULT false,
            prefers_concise_responses BOOLEAN NOT NULL DEFAULT false,
            preferences JSON,
            common_topics JSON,
            common_mistakes JSON,
            preferred_tools JSON,
            total_interactions INTEGER NOT NULL DEFAULT 0,
            avg_satisfaction FLOAT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_personas_tenant_id ON user_personas (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id VARCHAR(100) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            session_type VARCHAR(50),
            current_feature VARCHAR(100),
            message_count INTEGER NOT NULL DEFAULT 0,
            extra_metadata JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_agent_sessions_user_id ON agent_sessions (user_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_sessions_tenant_id ON agent_sessions (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_sessions_last_activity "
        "ON agent_sessions (last_activity_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_sessions_expires ON agent_sessions (expires_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            detected_feature VARCHAR(100),
            tools_used JSON,
            extra_metadata JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_session_messages_session_id ON session_messages (session_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_session_messages_tenant_id ON session_messages (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_session_messages_created_at ON session_messages (created_at)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_experiments (
            id VARCHAR(50) PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            prompt_template_id INTEGER NOT NULL REFERENCES prompt_templates(id),
            name VARCHAR(100) NOT NULL,
            description VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            start_time TIMESTAMPTZ NOT NULL DEFAULT now(),
            end_time TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prompt_experiments_tenant_id "
        "ON prompt_experiments (tenant_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_experiment_variants (
            experiment_id VARCHAR(50) NOT NULL REFERENCES prompt_experiments(id) ON DELETE CASCADE,
            variant_id VARCHAR(50) NOT NULL,
            content TEXT NOT NULL,
            is_control BOOLEAN NOT NULL,
            traffic_allocation FLOAT NOT NULL,
            PRIMARY KEY (experiment_id, variant_id)
        )
        """
    )

    # RLS: <tbl>_tenant_isolation pattern (20260529b_harden_user_persona_preferences...).
    # prompt_experiment_variants is deliberately excluded -- no tenant_id column.
    for tbl in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")
        op.execute(f"CREATE POLICY {tbl}_tenant_isolation ON {tbl} USING (tenant_id = {_RLS_EXPR})")


def downgrade() -> None:
    for tbl in _TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {tbl}_tenant_isolation ON {tbl}")

    op.execute("DROP TABLE IF EXISTS prompt_experiment_variants")
    op.execute("DROP TABLE IF EXISTS prompt_experiments")
    op.execute("DROP TABLE IF EXISTS session_messages")
    op.execute("DROP TABLE IF EXISTS agent_sessions")
    op.execute("DROP TABLE IF EXISTS user_personas")
    op.execute("DROP TABLE IF EXISTS prompt_metrics")
    op.execute("DROP TABLE IF EXISTS tool_definitions")
    op.execute("DROP TABLE IF EXISTS features")
    op.execute("DROP TABLE IF EXISTS prompt_templates")
