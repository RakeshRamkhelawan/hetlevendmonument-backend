"""Extra bestanden bij een verhaal (BE-EP-057), met RLS.

Revision ID: 20261103b_adr029_content_bestanden
Revises: 20261103_adr029_docentenomgeving
Create Date: 2026-11-03

Puur toevoegend: een NIEUWE tabel `foundation_content_bestanden` met Row Level Security.
Geen bestaande tabel, kolom of rij wordt gewijzigd. Het eerste bestand van een verhaal blijft
op `foundation_content.file_url` staan; deze tabel bevat alleen de bestanden daarna.

**Policyvorm: gelijk aan `20261103_adr029_docentenomgeving.py`**: `ENABLE ROW LEVEL SECURITY`
en een policy `FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true),
'')::INTEGER)`, in een DO-blok achter `to_regclass` en een `pg_policies`-controle.

`downgrade()` laat alleen deze tabel vallen. Let op: daarmee verdwijnen de verwijzingen naar
de extra bestanden; de bestanden zelf blijven in de opslag staan.

Geen `sa.inspect(op.get_bind())`: dat crasht bij een offline dry-run.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20261103b_adr029_content_bestanden"
down_revision = "20261103_adr029_docentenomgeving"
branch_labels = None
depends_on = None

_TABEL = "foundation_content_bestanden"
_POLICY = f"rls_{_TABEL}_tenant_isolation"
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite."""
    return op.get_bind().dialect.name == "postgresql"


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
            "content_id",
            sa.Integer(),
            sa.ForeignKey("foundation_content.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("volgorde", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.String(1024), nullable=False),
        sa.Column("file_mime", sa.String(100), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "content_id", "volgorde", name="uq_foundation_content_bestanden_volgorde"
        ),
    )
    op.create_index(f"ix_{_TABEL}_tenant_id", _TABEL, ["tenant_id"])
    op.create_index(f"ix_{_TABEL}_content_id", _TABEL, ["content_id"])

    if not _is_postgresql():
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
                    -- Dollar-quoting: de expressie bevat zelf enkele quotes.
                    EXECUTE $q$CREATE POLICY {_POLICY} ON {_TABEL} FOR ALL USING ({_EXPRESSIE})$q$;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    # Alleen wat upgrade() maakte; policy en indexen gaan met de tabel mee.
    op.drop_table(_TABEL)
