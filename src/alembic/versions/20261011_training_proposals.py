"""Nieuwe tabel `training_proposals`: een opleidingsvoorstel als rij (HR-pilot dag 2).

Revision ID: 20261011_training_proposals
Revises: 20261010_roi_tabellen
Create Date: 2026-10-11

Alleen TOEVOEGEND (interlock 1, aangekondigd in de dagbrief): een nieuwe tabel, geen bestaande
tabel, kolom of rij geraakt. `downgrade()` verwijdert precies deze tabel.

- `tenant_id NOT NULL` met vreemde sleutel naar `tenants` en een leidende index;
- Row Level Security: dezelfde policyvorm als `20261005_receivables_rls.py` (ENABLE, geen FORCE,
  DO-blok achter `to_regclass` en een `pg_policies`-controle, zodat een offline dry-run niet
  omvalt);
- status gesloten via een CHECK (`voorgesteld`, `goedgekeurd`, `afgewezen`);
- een gedeeltelijke unieke index: een medewerker heeft per vaardigheid hoogstens EEN open voorstel.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261011_training_proposals"
down_revision: str | None = "20261010_roi_tabellen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "training_proposals"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def upgrade() -> None:
    op.create_table(
        _TABEL,
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("skill_id", sa.Integer(), nullable=False),
        sa.Column("training_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="voorgesteld"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["training_id"], ["trainings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('voorgesteld','goedgekeurd','afgewezen')",
            name="ck_training_proposals_status",
        ),
    )
    op.create_index(f"ix_{_TABEL}_id", _TABEL, ["id"])
    op.create_index(f"ix_{_TABEL}_tenant_id", _TABEL, ["tenant_id"])
    op.create_index(f"ix_{_TABEL}_user_id", _TABEL, ["user_id"])
    op.create_index(f"ix_{_TABEL}_skill_id", _TABEL, ["skill_id"])
    op.create_index(f"ix_{_TABEL}_training_id", _TABEL, ["training_id"])
    op.create_index(
        "uq_training_proposals_open",
        _TABEL,
        ["tenant_id", "user_id", "skill_id"],
        unique=True,
        postgresql_where=sa.text("status = 'voorgesteld'"),
    )

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
    op.drop_index("uq_training_proposals_open", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_training_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_skill_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_user_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_tenant_id", table_name=_TABEL)
    op.drop_index(f"ix_{_TABEL}_id", table_name=_TABEL)
    op.drop_table(_TABEL)
