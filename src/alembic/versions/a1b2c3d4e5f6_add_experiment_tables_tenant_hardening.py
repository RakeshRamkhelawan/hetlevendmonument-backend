"""Add experiment tables to live chain, tenant_id NOT NULL, RLS

Revision ID: a1b2c3d4e5f6
Revises: 884d744f6aa9
Create Date: 2026-07-03

SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D): src/core/database/models/
experiment.py's 4 tables (experiments, experiment_variants, experiment_assignments,
experiment_events) were never part of the live Alembic chain -- a stale migration
exists under archive/ (20260329_add_experiment_tables.py) but no live migration
creates these tables (confirmed via grep across src/alembic/versions/*.py).

Per the same pre-launch/no-production-data precedent established in
884d744f6aa9 (agentic-domain tables, Dag 1 Groep 4): this migration creates the
CURRENT model schema directly (source of truth: src/core/database/models/
experiment.py), not the stale archived DDL, with experiments.tenant_id NOT NULL
from creation. A/B-testing experiments are inherently tenant-scoped (no
platform-wide-experiment use case found in the codebase) -- unlike
contact_opt_outs/email_bounces (see the companion migration in this same
sprint-day), there is no cross-tenant business reason for a nullable tenant_id
here.

experiment_variants/experiment_assignments/experiment_events have no tenant_id
column by design -- they are children of experiments (FK to experiments.id) and
inherit isolation via that FK, same pattern as prompt_experiment_variants in
884d744f6aa9.

backend-patterns.md #9: NOOIT sa.inspect(op.get_bind()) in migraties. Uses raw
"CREATE TABLE IF NOT EXISTS" / "DROP TABLE IF EXISTS" SQL, matching the
established pattern in 884d744f6aa9 / 20260404_gdpr_tables.py.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "884d744f6aa9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RLS_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::integer"


def upgrade() -> None:
    # SP-MIG-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 escalation, found during the
    # empty-database bootstrap verification for the audit_logs fix): an
    # "experiments" table already exists in the live chain since
    # 20260330_futureproof_baseline.py, with an incompatible legacy schema
    # (no tenant_id, no created_by, DATE instead of TIMESTAMPTZ). Because the
    # CREATE TABLE IF NOT EXISTS below silently no-ops against that legacy
    # table, a fresh database keeps the old shape and the CREATE INDEX on
    # created_by below fails with "column does not exist". Drop the legacy
    # experiments/experiment_participants pair first -- ONLY when experiments
    # is still in the legacy shape (missing created_by), so this is a no-op
    # against any database where this migration already ran. Same
    # pre-launch/no-production-data precedent as this file's own docstring.
    # experiment_participants has no ORM model and no application code
    # reference (confirmed via grep) -- it is dead, orphaned by the same
    # abandoned baseline design.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name = 'experiments'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'experiments' AND column_name = 'created_by'
            ) THEN
                DROP TABLE IF EXISTS experiment_participants CASCADE;
                DROP TABLE IF EXISTS experiments CASCADE;
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiments (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description VARCHAR(1000),
            start_date TIMESTAMPTZ NOT NULL,
            end_date TIMESTAMPTZ,
            status VARCHAR(20) NOT NULL DEFAULT 'draft',
            traffic_split FLOAT NOT NULL DEFAULT 0.5,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_by UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiments_status ON experiments (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiments_created_by ON experiments (created_by)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiments_start_date ON experiments (start_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_experiments_tenant_id ON experiments (tenant_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_variants (
            id UUID PRIMARY KEY,
            experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            config JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_variants_experiment_id "
        "ON experiment_variants (experiment_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_variants_name ON experiment_variants (name)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_assignments (
            id UUID PRIMARY KEY,
            experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            company_id UUID NOT NULL,
            variant VARCHAR(50) NOT NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ix_experiment_assignments_experiment_company
                UNIQUE (experiment_id, company_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_assignments_experiment_id "
        "ON experiment_assignments (experiment_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_assignments_company_id "
        "ON experiment_assignments (company_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS experiment_events (
            id UUID PRIMARY KEY,
            experiment_id UUID NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
            company_id UUID NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            variant VARCHAR(50) NOT NULL,
            event_metadata JSON,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_events_experiment_id "
        "ON experiment_events (experiment_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_events_company_id "
        "ON experiment_events (company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_events_event_type "
        "ON experiment_events (event_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_events_created_at "
        "ON experiment_events (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_experiment_events_experiment_variant "
        "ON experiment_events (experiment_id, variant)"
    )

    # RLS: <tbl>_tenant_isolation pattern -- experiments only (the 3 child tables
    # have no tenant_id column, isolation inherited via FK to experiments.id).
    op.execute("ALTER TABLE experiments ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS experiments_tenant_isolation ON experiments")
    op.execute(
        f"CREATE POLICY experiments_tenant_isolation ON experiments USING (tenant_id = {_RLS_EXPR})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS experiments_tenant_isolation ON experiments")
    op.execute("DROP TABLE IF EXISTS experiment_events")
    op.execute("DROP TABLE IF EXISTS experiment_assignments")
    op.execute("DROP TABLE IF EXISTS experiment_variants")
    op.execute("DROP TABLE IF EXISTS experiments")
