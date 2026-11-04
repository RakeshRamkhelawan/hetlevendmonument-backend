"""Tabel `foundation_archive_exports` met Row Level Security -- BagIt-archiefexport (BE-EP-054).

Revision ID: 20261102_adr029_archief_exports
Revises: 20261101_sync_merge_adr029_upstream_heads
Create Date: 2026-11-02

Puur toevoegend: een NIEUWE tabel, geen bestaande tabel, kolom of rij wordt geraakt, geen
backfill. `downgrade()` laat precies deze tabel vallen (policy en index gaan mee) en niets
anders.

**Policyvorm: gelijk aan `20261010_roi_tabellen.py`**: `ENABLE ROW LEVEL SECURITY` en een
policy `FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)`,
in een DO-blok achter `to_regclass` en een `pg_policies`-controle.

Geen `sa.inspect(op.get_bind())`: dat crasht bij een offline dry-run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261102_adr029_archief_exports"
down_revision = "20261101_sync_merge_adr029_upstream_heads"
branch_labels = None
depends_on = None

_TABEL = "foundation_archive_exports"
_RLS_TABELLEN = (_TABEL,)
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
        sa.Column("bag_name", sa.String(200), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("payload_file_count", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_url", sa.String(1024), nullable=False),
        sa.Column("trigger", sa.String(20), nullable=False),
        sa.Column(
            "created_by_portal_user_id",
            sa.Integer(),
            sa.ForeignKey("portal_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "trigger IN ('schema', 'handmatig')", name="ck_foundation_archive_exports_trigger"
        ),
    )
    op.create_index("ix_foundation_archive_exports_tenant_id", _TABEL, ["tenant_id"])

    if not _is_postgresql():
        return

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
    # Laat alleen de eigen tabel vallen; policy en index gaan met de tabel mee.
    op.drop_index("ix_foundation_archive_exports_tenant_id", table_name=_TABEL)
    op.drop_table(_TABEL)
