"""Tabel `receivables` (debiteuren) met Row Level Security -- debiteurenagent dag 1.

Revision ID: 20261005_receivables_rls
Revises: 20261004_user_roles_rls
Create Date: 2026-10-04

Puur toevoegend: een NIEUWE tabel, geen bestaande tabel, kolom of rij wordt geraakt, geen
backfill, geen demodata. `downgrade()` laat alleen deze tabel vallen.

**Policyvorm: gelijk aan `20260915_rls_resterende_tabellen.py`.** `ENABLE ROW LEVEL
SECURITY` en een policy `FOR ALL USING (tenant_id = NULLIF(current_setting(
'app.current_tenant', true), '')::INTEGER)`, in een DO-blok achter `to_regclass` en een
`pg_policies`-controle. Geen `FORCE`, geen rol, geen wijziging aan de bypassverbinding.
`USING` zonder `WITH CHECK` geldt bij INSERT en UPDATE ook als `WITH CHECK` (PostgreSQL 15,
CREATE POLICY); gemeten in `tests/integration/security/test_receivables_is_confined_to_its_tenant.py`.

De leidende index op `tenant_id` (`ix_receivables_tenant_id`) staat in deze migratie omdat de
tabel nieuw is; zonder hem valt elke RLS-query terug op een sequential scan (OP-161).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261005_receivables_rls"
down_revision = "20261004_user_roles_rls"
branch_labels = None
depends_on = None

_TABEL = "receivables"
_RLS_TABELLEN = ("receivables",)
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
        sa.Column("customer_name", sa.String(length=200), nullable=False),
        sa.Column("customer_email", sa.String(length=320), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "tenant_id", "source", "external_id", name="uq_receivables_tenant_source_external"
        ),
        sa.CheckConstraint(
            "status IN ('open', 'herinnerd', 'betaald')", name="ck_receivables_status"
        ),
        sa.CheckConstraint(
            "source IN ('handmatig', 'import', 'koppeling')", name="ck_receivables_source"
        ),
        sa.CheckConstraint(
            "(source = 'handmatig') = (external_id IS NULL)",
            name="ck_receivables_external_id_matches_source",
        ),
    )
    op.create_index("ix_receivables_tenant_id", _TABEL, ["tenant_id"])

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
    op.drop_index("ix_receivables_tenant_id", table_name=_TABEL)
    op.drop_table(_TABEL)
