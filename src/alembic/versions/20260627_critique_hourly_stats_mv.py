"""critique_hourly_stats materialized view for telemetry (SP-AGT-006 Dag 3)

Revision ID: 20260627_critique_hourly_stats_mv
Revises: 20260627_add_tenant_id_experiments
Create Date: 2026-06-27

Creates a PostgreSQL materialized view that aggregates agent_critiques by hour,
tenant_id, and agent_name. Used by GET /critics/telemetry for time-series queries
without full-table scans.

Refresh: CONCURRENTLY via CritiqueStore._refresh_mv() (5 min cooldown, best_effort).
Downgrade: fully reversible via DROP MATERIALIZED VIEW.
"""

from alembic import op

revision = "20260627_critique_hourly_stats_mv"
down_revision = "20260627_add_tenant_id_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS critique_hourly_stats AS
        SELECT
            DATE_TRUNC('hour', created_at) AS hour,
            tenant_id,
            agent_name,
            AVG(score)::float AS avg_score,
            COUNT(*)::int AS critique_count
        FROM agent_critiques
        GROUP BY 1, 2, 3
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_critique_hourly_stats_unique
        ON critique_hourly_stats (hour, tenant_id, agent_name)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_critique_hourly_stats_unique")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS critique_hourly_stats")
