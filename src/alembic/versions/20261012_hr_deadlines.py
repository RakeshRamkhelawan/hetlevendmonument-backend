"""Nieuwe tabel `hr_deadlines`: termijnen voor de HR-pilot (dag 3).

Revision ID: 20261012_hr_deadlines
Revises: 20261011_training_proposals
Create Date: 2026-10-12

Alleen TOEVOEGEND (interlock 1, aangekondigd in de dagbrief): een nieuwe tabel, geen bestaande
tabel, kolom of rij geraakt. `downgrade()` verwijdert precies deze tabel.

- `tenant_id NOT NULL` met vreemde sleutel naar `tenants` en een leidende index;
- Row Level Security: dezelfde policyvorm als `20261011_training_proposals.py` (ENABLE, geen FORCE,
  DO-blok achter `to_regclass` en een `pg_policies`-controle, zodat een offline dry-run niet
  omvalt);
- soort en status gesloten via CHECK;
- een CHECK die afdwingt dat verzuim GEEN omschrijving heeft: de werkgever mag de aard of oorzaak
  van de ziekte niet registreren (Autoriteit Persoonsgegevens), dus de database laat het niet toe.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261012_hr_deadlines"
down_revision: str | None = "20261011_training_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "hr_deadlines"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("analysis_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("done_labels", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('contract_einde','verzuim','certificaat')", name="ck_hr_deadlines_kind"
        ),
        sa.CheckConstraint("status IN ('open','afgerond')", name="ck_hr_deadlines_status"),
        sa.CheckConstraint(
            "(kind = 'verzuim' AND start_date IS NOT NULL AND description IS NULL) "
            "OR (kind IN ('contract_einde','certificaat') AND end_date IS NOT NULL)",
            name="ck_hr_deadlines_dates",
        ),
    )
    op.create_index(f"ix_{_TABEL}_id", _TABEL, ["id"])
    op.create_index(f"ix_{_TABEL}_tenant_id", _TABEL, ["tenant_id"])
    op.create_index(f"ix_{_TABEL}_user_id", _TABEL, ["user_id"])

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
    # De policy gaat mee met de tabel; alleen de tabel en zijn indexen bestaan door deze migratie.
    op.drop_index(f"ix_{_TABEL}_user_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_tenant_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_id", table_name=_TABEL)
    op.drop_table(_TABEL)
