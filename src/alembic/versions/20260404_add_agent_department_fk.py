"""Add department_id to agents table

Revision ID: 20260404_add_agent_department_fk
Revises: 20260404_gdpr_tables
Create Date: 2026-04-04

This migration is written defensively:
- Creates the agents table if it does not exist.  This is a safety net for
  databases that were left in a broken intermediate state (baseline stamp ran
  but baseline SQL did not execute).  On a clean database the CREATE is a no-op.
  NOTE: this migration is NOT intended for use on a truly empty database; the
  ``tenants`` and ``departments`` tables are assumed to exist (created by the
  baseline and GDPR migrations that precede this one).
- Adds department_id only if the column is not already present (idempotent for
  production databases that may already have the column from older migrations).
- FK existence checks are scoped to the ``agents`` table via ``conrelid`` to
  avoid false positives if another table happens to have a same-named constraint.
- All DDL uses IF NOT EXISTS / conditional blocks so the migration is safe to
  re-run against any partially-applied database state.
"""

from alembic import op

revision = "20260404_add_agent_department_fk"
down_revision = "20260404_gdpr_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Ensure agents table exists (safety net for broken DB states).
    #    The baseline migration also creates this table; using IF NOT EXISTS
    #    means this is a no-op when the baseline ran correctly.
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 2. Add department_id column -- skip if already present.
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE agents
            ADD COLUMN IF NOT EXISTS department_id UUID
        """
    )

    # ------------------------------------------------------------------
    # 3. Add FK constraint -- skip if it already exists.
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_agents_department'
                  AND conrelid = 'agents'::regclass
            ) THEN
                ALTER TABLE agents
                    ADD CONSTRAINT fk_agents_department
                        FOREIGN KEY (department_id)
                        REFERENCES departments(id)
                        ON DELETE SET NULL;
            END IF;
        END
        $$
        """
    )

    # ------------------------------------------------------------------
    # 4. Add index -- skip if already present.
    # ------------------------------------------------------------------
    op.execute("CREATE INDEX IF NOT EXISTS idx_agents_department ON agents(department_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_agents_department")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_agents_department'
                  AND conrelid = 'agents'::regclass
            ) THEN
                ALTER TABLE agents DROP CONSTRAINT fk_agents_department;
            END IF;
        END
        $$
        """
    )
    op.execute(
        """
        ALTER TABLE agents
            DROP COLUMN IF EXISTS department_id
        """
    )
