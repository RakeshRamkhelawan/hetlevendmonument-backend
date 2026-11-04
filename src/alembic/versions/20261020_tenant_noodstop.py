"""Nieuwe tabel `tenant_noodstop`: staat een klant stil (noodstop per klant).

Revision ID: 20261020_tenant_noodstop
Revises: 20261024_payables_rls
Create Date: 2026-10-20

Alleen TOEVOEGEND (interlock 1, aangekondigd in de dagbrief): een nieuwe tabel, geen bestaande
tabel, kolom of rij geraakt. `downgrade()` verwijdert precies deze tabel. Gevolg: na deze wijziging
staat elke klant NIET stil, tot een beheerder de noodstop zet.

- `tenant_id NOT NULL` met vreemde sleutel naar `tenants` en een leidende index;
- unieke `tenant_id`: een klant heeft hoogstens een rij;
- `reden` met een lengtegrens via CHECK (`length`, zodat ook de SQLite-tabellen van de unit-tests
  hem kunnen aanmaken);
- Row Level Security: dezelfde policyvorm als `20261014_pack_activations.py` (ENABLE, geen FORCE,
  DO-blok achter `to_regclass` en een `pg_policies`-controle, zodat een offline dry-run niet
  omvalt).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_tenant_noodstop"
down_revision: str | None = "20261024_payables_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "tenant_noodstop"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("is_stilgezet", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reden", sa.String(length=500), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "changed_by_platform", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_noodstop_tenant"),
        sa.CheckConstraint(
            "reden IS NULL OR length(reden) BETWEEN 1 AND 500",
            name="ck_tenant_noodstop_reden_lengte",
        ),
    )
    op.create_index(f"ix_{_TABEL}_id", _TABEL, ["id"])
    op.create_index(f"ix_{_TABEL}_tenant_id", _TABEL, ["tenant_id"])

    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF to_regclass('public.{_TABEL}') IS NULL THEN
                    RETURN;
                END IF;
                EXECUTE 'ALTER TABLE {_TABEL} ENABLE ROW LEVEL SECURITY';
                IF NOT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public' AND tablename = '{_TABEL}'
                      AND policyname = '{_POLICY}'
                ) THEN
                    EXECUTE $q$CREATE POLICY {_POLICY} ON {_TABEL} FOR ALL USING ({_EXPRESSIE})$q$;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # De policy en de unieke constraint gaan mee met de tabel; alleen de tabel en zijn indexen
    # bestaan door deze migratie.
    op.drop_index(f"ix_{_TABEL}_tenant_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_id", table_name=_TABEL)
    op.drop_table(_TABEL)
