"""Nieuwe tabel `tenant_ap_verbindingen`: de ActivePieces-verbinding van een klant.

Revision ID: 20261020_tenant_ap_verbindingen
Revises: 20261014_pack_activations
Create Date: 2026-10-20

Alleen TOEVOEGEND (interlock 1, door Rakesh gegeven: "ja migratie AP"): een nieuwe tabel, geen
bestaande tabel, kolom of rij geraakt. `downgrade()` verwijdert precies deze tabel.

- een rij per klant: `tenant_id` is UNIQUE, want een klant heeft een eigen ActivePieces-project;
- `tenant_id NOT NULL` met vreemde sleutel naar `tenants` (ON DELETE CASCADE) en een index;
- `wachtwoord_encrypted` bevat NOOIT een leesbaar wachtwoord: de servicelaag versleutelt via
  `src/core/security/tenant_secret_encryption.py` voordat er iets wordt opgeslagen;
- Row Level Security: dezelfde policyvorm als `20261014_pack_activations.py` (ENABLE, geen
  FORCE, DO-blok achter `to_regclass` en een `pg_policies`-controle, zodat een offline dry-run
  niet omvalt).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261020_tenant_ap_verbindingen"
down_revision: str | None = "20261014_pack_activations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "tenant_ap_verbindingen"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("base_url", sa.String(length=512), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("wachtwoord_encrypted", sa.Text(), nullable=False),
        sa.Column("project_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_ap_verbindingen_tenant"),
        # Twee tenants mogen nooit hetzelfde AP-project delen: de eigenaarstoets van id's
        # vergelijkt het project, en bij een gedeeld project ziet tenant B alles van tenant A
        # (Gate 2 dag 2, M2). Een typefout van de beheerder wordt zo een weigering.
        sa.UniqueConstraint("base_url", "project_id", name="uq_tenant_ap_verbindingen_adres_project"),
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
