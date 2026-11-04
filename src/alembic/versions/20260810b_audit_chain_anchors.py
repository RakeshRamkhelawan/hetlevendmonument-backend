"""Anker per tenant voor de auditketen (ADR-036 OP-118/OP-119).

`verify_chain` leest alleen `audit_logs`, en afwezigheid heeft geen hash: verdwenen rijen zijn per
constructie onzichtbaar voor een staatloze controle. Gemeten gevolg:
`DELETE FROM audit_logs WHERE tenant_id = X` gaf `is_valid=True`, en een lege keten heet in
`get_chain_status` letterlijk `status="healthy", health_percentage=100.0`.

Deze tabel onthoudt per tenant wat er de vorige keer stond -- kop, aantal regels en het aantal
regels zonder hash -- zodat een DALING zichtbaar wordt. `chain_epoch_id` is het knippunt voor de
HMAC-omschakeling (OP-120) en blijft tot die tijd leeg.

RLS conform ADR-005, naar het patroon van `20260706_add_agentic_tasks_table.py`. Bewust GEEN
`sa.inspect(op.get_bind())` -- dat crasht bij een offline dry-run
(`.claude/rules/backend-patterns.md` par. 9, bewaakt door
`tests/architecture/test_no_sa_inspect_in_migrations.py`).

Revision ID: 20260810b_audit_chain_anchors
Revises: 20260810_audit_chain_lookup_index
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810b_audit_chain_anchors"
down_revision: str | None = "20260810_audit_chain_lookup_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "audit_chain_anchors"
_POLICY = "audit_chain_anchor_tenant_isolation"


def _is_offline() -> bool:
    """Detect Alembic offline (--sql) mode to skip runtime-only DDL."""
    import sqlalchemy.engine.mock as mock_mod

    return isinstance(op.get_bind(), mock_mod.MockConnection)


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # NULL betekent "de keten was leeg bij de vorige meting". Dat is iets anders dan "nooit
        # gemeten" -- in dat geval bestaat deze rij niet, en dan alarmeert de job bewust niet.
        sa.Column("head_hash", sa.String(length=64), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unhashed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        # Knippunt voor OP-120. Leeg tot de HMAC-omschakeling; daarna is een ongesleutelde rij
        # NA dit punt zelf een afwijking.
        sa.Column("chain_epoch_id", sa.Integer(), nullable=True),
    )

    if _is_postgresql() and not _is_offline():
        op.execute(sa.text(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}"))
        op.execute(
            sa.text(
                f"CREATE POLICY {_POLICY} ON {_TABLE} "
                "FOR ALL USING ("
                "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                ")"
            )
        )


def downgrade() -> None:
    if _is_postgresql() and not _is_offline():
        op.execute(sa.text(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}"))
        op.execute(sa.text(f"ALTER TABLE {_TABLE} DISABLE ROW LEVEL SECURITY"))

    op.drop_table(_TABLE)
