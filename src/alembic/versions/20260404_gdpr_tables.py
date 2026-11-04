"""GDPR compliance tables

Revision ID: 20260404_gdpr_tables
Revises: 20260330_futureproof_baseline
Create Date: 2026-04-04 14:40:00.000000

"""

from typing import Union
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260404_gdpr_tables"
down_revision: str | None = "20260330_futureproof_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create GDPR compliance tables using raw SQL with IF NOT EXISTS.

    NOTE: GDPR tables use PostgreSQL-specific types (SERIAL, TIMESTAMP WITH TIME ZONE, JSONB, BOOLEAN).
    On SQLite (CI offline mode), these tables are skipped -- they will be created online in production.
    """

    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    if is_sqlite:
        # Skip GDPR tables on SQLite -- they use PostgreSQL-specific types
        # In offline mode (CI dry-run), this whole section is skipped.
        # In production (PostgreSQL), these tables are created.
        op.execute(
            sa.text(
                "-- Skipped on SQLite: user_consents, ai_decisions, user_profiling_opt_outs, "
                "human_review_requests, dsar_requests (PostgreSQL-specific types)"
            )
        )
    else:
        # Create user_consents table for cookie consent management
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS user_consents (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                tenant_id INTEGER NOT NULL,
                essential BOOLEAN NOT NULL DEFAULT TRUE,
                analytics BOOLEAN NOT NULL DEFAULT FALSE,
                marketing BOOLEAN NOT NULL DEFAULT FALSE,
                personalization BOOLEAN NOT NULL DEFAULT FALSE,
                policy_version VARCHAR(50) NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT uq_user_tenant_consent UNIQUE (user_id, tenant_id)
            )
        """
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_user_consents_user_id ON user_consents (user_id)")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_user_consents_tenant_id ON user_consents (tenant_id)"
        )

        # Create ai_decisions table for AI transparency
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                tenant_id INTEGER NOT NULL,
                agent_id VARCHAR(255) NOT NULL,
                decision_type VARCHAR(100) NOT NULL,
                input_data JSONB,
                output_data JSONB,
                confidence_score FLOAT,
                explanation TEXT NOT NULL,
                profiling_involved BOOLEAN NOT NULL DEFAULT FALSE,
                human_review_available BOOLEAN NOT NULL DEFAULT TRUE,
                human_review_requested BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_decisions_user_id ON ai_decisions (user_id)")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_ai_decisions_tenant_id ON ai_decisions (tenant_id)"
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_ai_decisions_agent_id ON ai_decisions (agent_id)")
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_ai_decisions_created_at ON ai_decisions (created_at)"
        )

        # Create user_profiling_opt_outs table for Art. 21
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiling_opt_outs (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                tenant_id INTEGER NOT NULL,
                profiling_type VARCHAR(50) NOT NULL,
                opted_out BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE,
                CONSTRAINT uq_user_profiling_opt_out UNIQUE (user_id, tenant_id, profiling_type)
            )
        """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_profiling_opt_outs_user_id ON user_profiling_opt_outs (user_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_profiling_opt_outs_tenant_id ON user_profiling_opt_outs (tenant_id)"
        )

        # Create human_review_requests table for Art. 22(3)
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS human_review_requests (
                id SERIAL PRIMARY KEY,
                decision_id INTEGER NOT NULL,
                user_id VARCHAR(255) NOT NULL,
                reason TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                reviewer_id INTEGER,
                reviewer_notes TEXT,
                reviewed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_human_review_decision_id ON human_review_requests (decision_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_human_review_user_id ON human_review_requests (user_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_human_review_status ON human_review_requests (status)"
        )

        # Create dsar_requests table for Data Subject Access Requests
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS dsar_requests (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                tenant_id INTEGER NOT NULL,
                request_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                requested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                completed_at TIMESTAMP WITH TIME ZONE,
                data_url VARCHAR(500),
                is_admin_request BOOLEAN NOT NULL DEFAULT FALSE
            )
        """
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_dsar_user_id ON dsar_requests (user_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_dsar_tenant_id ON dsar_requests (tenant_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_dsar_status ON dsar_requests (status)")


def downgrade() -> None:
    """Drop GDPR compliance tables."""
    op.execute("DROP TABLE IF EXISTS dsar_requests")
    op.execute("DROP TABLE IF EXISTS human_review_requests")
    op.execute("DROP TABLE IF EXISTS user_profiling_opt_outs")
    op.execute("DROP TABLE IF EXISTS ai_decisions")
    op.execute("DROP TABLE IF EXISTS user_consents")
