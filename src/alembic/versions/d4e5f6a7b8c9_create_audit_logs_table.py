"""create audit_logs table

Revision ID: d4e5f6a7b8c9
Revises: 20260623_add_rls_conversations
Create Date: 2026-07-04

SP-MIG-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 escalation): the live Alembic chain
could not bootstrap audit_logs from an empty database. The only migration
that ever created this table lives at
src/alembic/versions/archive/fix_audit_logs_table.py -- archived (outside the
live chain), and its CREATE TABLE call was already a no-op (commented out,
guarded by "if not insp.has_table(...)") before archival. A fresh database
fails on 0092fdf7d725_add_audit_log_hash_chain_fields.py's
"ALTER TABLE audit_logs ADD COLUMN audit_hash" because the table never
existed in the live chain.

Schema matches src/core/models/audit_log.py::AuditLog exactly (confirmed via
direct read), EXCLUDING audit_hash/previous_hash -- those two columns are
added by 0092fdf7d725 immediately after this migration, adding them here too
would raise a duplicate-column error.

audit_logs is intentionally excluded from RLS (see
20260522_add_rls_core_tables.py's own docstring: "outside the ORM auto-filter
by design", fail-secure RuntimeError pattern enforced in application code
instead of a DB policy) -- this migration does not add RLS either.

backend-patterns.md #9: NOOIT sa.inspect(op.get_bind()) in migraties. Uses raw
"CREATE TABLE IF NOT EXISTS" SQL, matching the established pattern.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "20260623_add_rls_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER REFERENCES tenants(id),
            action VARCHAR,
            resource VARCHAR,
            details JSON,
            event_type VARCHAR(100) NOT NULL,
            threat_level VARCHAR(20) NOT NULL,
            client_ip VARCHAR(45) NOT NULL,
            endpoint TEXT NOT NULL,
            description TEXT NOT NULL,
            event_metadata JSON NOT NULL,
            user_id INTEGER REFERENCES users(id),
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id ON audit_logs (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_event_type ON audit_logs (event_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_threat_level ON audit_logs (threat_level)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_client_ip ON audit_logs (client_ip)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON audit_logs (timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
