"""Tabellen `suppliers` en `payables` (crediteuren) met Row Level Security -- Keten F dag 1.

Revision ID: 20261024_payables_rls
Revises: 20261023_schemadrift_schadelijk
Create Date: 2026-10-24

Puur TOEVOEGEND (interlock 1): twee NIEUWE tabellen, geen bestaande tabel, kolom of rij wordt geraakt, geen backfill, geen
demodata. `downgrade()` laat alleen deze twee tabellen vallen (eerst `payables`, dat naar `suppliers` verwijst).

**Policyvorm: gelijk aan `20261005_receivables_rls.py`.** `ENABLE ROW LEVEL SECURITY` en een policy `FOR ALL USING (tenant_id =
NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)`, in een DO-blok achter `to_regclass` en een
`pg_policies`-controle. Geen `FORCE`, geen rol, geen wijziging aan de bypassverbinding.

**Samengestelde sleutel.** `payables (tenant_id, supplier_id)` verwijst naar `suppliers (tenant_id, id)`: een factuur kan niet
naar de leverancier van een ander bedrijf wijzen, ook niet voor de eigenaar (die RLS omzeilt). Daarvoor heeft `suppliers` een
unieke sleutel op `(tenant_id, id)`.

**Geld is een geheel aantal centen** (`amount_cents BIGINT`, groter dan nul). De CHECKs op status, bedrag, valuta en
vervaldatum zijn het vangnet onder de repository; ze gebruiken bewust geen regex (`~` is PostgreSQL).

**Geen dubbele leverancier of factuur, hoofdletterongevoelig.** Unieke indexen op `(tenant_id, lower(name))` en
`(tenant_id, supplier_id, lower(invoice_number))`: "INK-1" en "ink-1" zijn een factuur.

De leidende index op `tenant_id` staat in deze migratie omdat de tabellen nieuw zijn; zonder hem valt elke RLS-query terug op een
sequential scan (OP-161).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_payables_rls"
down_revision: str | None = "20261023_schemadrift_schadelijk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABELLEN = ("suppliers", "payables")
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def _policynaam(tabel: str) -> str:
    return f"rls_{tabel}_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("iban", sa.String(length=34), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id_id"),
    )
    op.create_index("ix_suppliers_tenant_id", "suppliers", ["tenant_id"])
    # Hoofdletterongevoelig (Gate 2): "Acme BV" en "ACME BV" zijn een leverancier; dubbel betalen is het risico van crediteuren.
    op.create_index(
        "uq_suppliers_tenant_lower_name", "suppliers", ["tenant_id", sa.text("lower(name)")], unique=True
    )

    op.create_table(
        "payables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("invoice_number", sa.String(length=100), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "checked_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_payables_tenant_supplier",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('ontvangen', 'gecontroleerd', 'goedgekeurd', 'in_betaalbestand', 'betaald', 'afgewezen')",
            name="ck_payables_status",
        ),
        sa.CheckConstraint("amount_cents > 0", name="ck_payables_amount_positive"),
        sa.CheckConstraint(
            "length(currency) = 3 AND currency = upper(currency)", name="ck_payables_currency_iso"
        ),
        sa.CheckConstraint("due_date >= invoice_date", name="ck_payables_due_after_invoice"),
    )
    op.create_index("ix_payables_tenant_id", "payables", ["tenant_id"])
    op.create_index(
        "uq_payables_tenant_supplier_lower_invoice",
        "payables",
        ["tenant_id", "supplier_id", sa.text("lower(invoice_number)")],
        unique=True,
    )

    if op.get_bind().dialect.name != "postgresql":
        # RLS bestaat niet in SQLite (offline dry-run en unit-tests).
        return

    # Lus-idioom van 20260915_rls_resterende_tabellen.py: de architecture-guard lost `{tabel}` op via de lus en ziet zo de
    # tabelnamen in de SQL.
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
    # Laat alleen de eigen tabellen vallen, eerst de verwijzende; de policies, sleutels en CHECKs gaan met de tabellen mee.
    op.drop_index("uq_payables_tenant_supplier_lower_invoice", table_name="payables")
    op.drop_index("ix_payables_tenant_id", table_name="payables")
    op.drop_table("payables")
    op.drop_index("uq_suppliers_tenant_lower_name", table_name="suppliers")
    op.drop_index("ix_suppliers_tenant_id", table_name="suppliers")
    op.drop_table("suppliers")
