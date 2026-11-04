"""Nieuwe tabel `tenant_pack_activations`: welk pakket staat voor welke klant aan.

Revision ID: 20261014_pack_activations
Revises: 20261012_audit_geen_tenant_fk
Create Date: 2026-10-14

Alleen TOEVOEGEND (interlock 1, aangekondigd in de dagbrief): een nieuwe tabel, geen bestaande
tabel, kolom of rij geraakt. `downgrade()` verwijdert precies deze tabel. Gevolg: na deze wijziging
staat elk pakket voor elke klant UIT, tot een beheerder het aanzet.

- `tenant_id NOT NULL` met vreemde sleutel naar `tenants` en een leidende index;
- unieke (tenant, pack): een pakket heeft per klant hoogstens een rij;
- `pack_id` is de catalogus-id als tekst (de catalogus staat in een configuratiebestand, dus geen
  vreemde sleutel) met een lengtegrens via CHECK (`length`, zodat ook de SQLite-tabellen van de
  unit-tests hem kunnen aanmaken);
- Row Level Security: dezelfde policyvorm als `20261012_hr_deadlines.py` (ENABLE, geen FORCE,
  DO-blok achter `to_regclass` en een `pg_policies`-controle, zodat een offline dry-run niet
  omvalt).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_pack_activations"
down_revision: str | None = "20261012_audit_geen_tenant_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "tenant_pack_activations"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("pack_id", sa.String(length=100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("enabled_by_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "enabled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["enabled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "pack_id", name="uq_tenant_pack_activations_tenant_pack"),
        sa.CheckConstraint(
            "length(pack_id) BETWEEN 1 AND 100",
            name="ck_tenant_pack_activations_pack_id_lengte",
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
