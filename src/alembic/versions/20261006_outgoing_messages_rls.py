"""Tabel `outgoing_messages` (uitgaande berichten) met Row Level Security -- debiteurenagent dag 2.

Revision ID: 20261006_outgoing_messages_rls
Revises: 20261005_receivables_rls
Create Date: 2026-10-05

Puur toevoegend: een NIEUWE tabel, geen bestaande tabel, kolom of rij wordt geraakt, geen
backfill, geen demodata. `downgrade()` laat alleen deze tabel vallen.

**Policyvorm: gelijk aan `20261005_receivables_rls.py`** (die weer gelijk is aan
`20260915_rls_resterende_tabellen.py`): `ENABLE ROW LEVEL SECURITY` en een policy `FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)`, in een
DO-blok achter `to_regclass` en een `pg_policies`-controle. Geen `FORCE`, geen rol, geen
wijziging aan de bypassverbinding (OP-151).

De leidende index op `tenant_id` staat in deze migratie omdat de tabel nieuw is (OP-161).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261006_outgoing_messages_rls"
down_revision = "20261005_receivables_rls"
branch_labels = None
depends_on = None

_TABEL = "outgoing_messages"
_RLS_TABELLEN = ("outgoing_messages",)
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite."""
    return op.get_bind().dialect.name == "postgresql"


def _policynaam(tabel: str) -> str:
    return f"rls_{tabel}_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "receivable_id",
            sa.Integer(),
            sa.ForeignKey("receivables.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("hitl_ticket_ref", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("hitl_ticket_ref"),
        sa.CheckConstraint("channel IN ('email')", name="ck_outgoing_messages_channel"),
        sa.CheckConstraint(
            "kind IN ('herinnering', 'aanmaning')", name="ck_outgoing_messages_kind"
        ),
        sa.CheckConstraint(
            "status IN ('klaar', 'verzonden', 'mislukt')", name="ck_outgoing_messages_status"
        ),
    )
    op.create_index("ix_outgoing_messages_tenant_id", _TABEL, ["tenant_id"])

    if not _is_postgresql():
        return

    # Lus-idioom van 20260915_rls_resterende_tabellen.py, ook voor een enkele tabel: de
    # architecture-guard lost `{tabel}` op via de lus en ziet zo de tabelnaam in de SQL.
    for tabel in _RLS_TABELLEN:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{tabel}') IS NULL THEN
                        RETURN;
                    END IF;
                    EXECUTE 'ALTER TABLE {tabel} ENABLE ROW LEVEL SECURITY';
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE schemaname = 'public' AND tablename = '{tabel}'
                          AND policyname = '{_policynaam(tabel)}'
                    ) THEN
                        -- Dollar-quoting: de expressie bevat zelf enkele quotes.
                        EXECUTE $q$CREATE POLICY {_policynaam(tabel)} ON {tabel} FOR ALL USING ({_EXPRESSIE})$q$;
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    # Laat alleen de eigen tabel vallen; de policy en de index gaan met de tabel mee.
    op.drop_index("ix_outgoing_messages_tenant_id", table_name=_TABEL)
    op.drop_table(_TABEL)
