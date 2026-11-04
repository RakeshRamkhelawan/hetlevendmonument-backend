"""Partiele index voor de ketenlookup op audit_logs (ADR-036 OP-108).

Elke auditschrijving doet eerst deze query, onder een `pg_advisory_xact_lock`:

    SELECT audit_hash FROM audit_logs
    WHERE tenant_id = :t AND audit_hash IS NOT NULL
    ORDER BY timestamp DESC, id DESC
    LIMIT 1

Er was geen index op `audit_hash`, dus dit werd een filter-plus-sortering bovenop
`ix_audit_logs_tenant_id` -- op een grote tenant een kostenpost per schrijving, gehouden onder
een lock dat alle andere schrijvers van die tenant tegenhoudt. De bestaande indexen op deze
tabel zijn allemaal enkelkoloms; er is geen samengestelde `(tenant_id, timestamp)`, dus geen
overlap.

`postgresql_where` is dialect-gebonden: SQLAlchemy zendt het alleen op PostgreSQL. Een expliciete
`_is_postgresql()`-guard is hier dus niet nodig -- en `sa.inspect(op.get_bind())` MAG sowieso niet
(`.claude/rules/backend-patterns.md` par. 9, bewaakt door
`tests/architecture/test_no_sa_inspect_in_migrations.py`): dat crasht bij een offline dry-run.

Bewust een gewone `CREATE INDEX` en geen `CONCURRENTLY`: dat laatste kan niet binnen de
transactie waarin alembic zijn migraties draait, en botst met de offline `--sql`-modus die
`scripts/pre-deploy-check.sh` gebruikt.

Revision ID: 20260810_audit_chain_lookup_index
Revises: 20260806_hitl_resolution_note
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_audit_chain_lookup_index"
down_revision: str | None = "20260806_hitl_resolution_note"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "ix_audit_logs_chain_lookup"


def upgrade() -> None:
    op.create_index(
        _INDEX_NAME,
        "audit_logs",
        ["tenant_id", sa.text("timestamp DESC"), sa.text("id DESC")],
        unique=False,
        postgresql_where=sa.text("audit_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="audit_logs")
