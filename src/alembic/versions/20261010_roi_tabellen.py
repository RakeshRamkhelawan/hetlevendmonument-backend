"""Tabellen `agent_run_metrics` en `roi_assumptions` met Row Level Security -- ROI eerlijk gemeten.

Revision ID: 20261010_roi_tabellen
Revises: 20261009_user_roles_tenant_id
Create Date: 2026-10-10

Puur toevoegend: twee NIEUWE tabellen, geen bestaande tabel, kolom of rij wordt geraakt, geen
backfill, geen demodata. `downgrade()` laat precies deze twee tabellen vallen (de policy en de
indexen gaan met de tabel mee) en niets anders. Interlock 1 is door Rakesh ("inzake de roi, regel
dit zelf") aan de regie overgelaten onder die voorwaarde; dit bestand houdt zich eraan.

De tabel `agent_execution_logs` waar `ROIService.log_execution` naartoe schreef bestond in geen
model en geen migratie (gemeten 2026-10-09, OP-09); er is dus niets om te migreren of te laten
vallen.

**Geen medewerkersveld.** Geen `user_id`, naam, e-mail of afdeling in `agent_run_metrics`: ROI per
persoon is monitoring (WOR art. 27 lid 1 sub l, AVG art. 88).

**Policyvorm: gelijk aan `20261006_outgoing_messages_rls.py`**: `ENABLE ROW LEVEL SECURITY` en een
policy `FOR ALL USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER)`,
in een DO-blok achter `to_regclass` en een `pg_policies`-controle. Geen `FORCE`, geen rol, geen
wijziging aan de bypassverbinding (OP-151). De leidende index op `tenant_id` staat hier omdat de
tabellen nieuw zijn (OP-161).

Geen `sa.inspect(op.get_bind())`: dat crasht bij een offline dry-run.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261010_roi_tabellen"
down_revision = "20261009_user_roles_tenant_id"
branch_labels = None
depends_on = None

_RUNS = "agent_run_metrics"
_AANNAMES = "roi_assumptions"
_RLS_TABELLEN = (_RUNS, _AANNAMES)
_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite."""
    return op.get_bind().dialect.name == "postgresql"


def _policynaam(tabel: str) -> str:
    return f"rls_{tabel}_tenant_isolation"


def upgrade() -> None:
    op.create_table(
        _RUNS,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pack_id", sa.String(length=100), nullable=True),
        sa.Column("agent_id", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("items_processed", sa.Integer(), nullable=True),
        sa.Column(
            "needed_human_review", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("llm_cost_eur", sa.Numeric(12, 4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('klaar', 'gedeeltelijk', 'meer_budget_nodig', 'geblokkeerd', 'mislukt')",
            name="ck_agent_run_metrics_status",
        ),
        sa.CheckConstraint(
            "items_processed IS NULL OR items_processed >= 0",
            name="ck_agent_run_metrics_items_processed",
        ),
        sa.CheckConstraint(
            "llm_cost_eur IS NULL OR llm_cost_eur >= 0", name="ck_agent_run_metrics_llm_cost_eur"
        ),
    )
    op.create_index("ix_agent_run_metrics_tenant_id", _RUNS, ["tenant_id"])

    op.create_table(
        _AANNAMES,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Integer(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pack_id", sa.String(length=100), nullable=False),
        sa.Column("manual_minutes_per_item", sa.Numeric(10, 2), nullable=False),
        sa.Column("hourly_rate_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="klant_ingevuld"),
        sa.Column(
            "set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", "pack_id", name="uq_roi_assumptions_tenant_pack"),
        sa.CheckConstraint(
            "manual_minutes_per_item > 0", name="ck_roi_assumptions_manual_minutes_per_item"
        ),
        sa.CheckConstraint("hourly_rate_eur >= 0", name="ck_roi_assumptions_hourly_rate_eur"),
        sa.CheckConstraint("source IN ('klant_ingevuld')", name="ck_roi_assumptions_source"),
    )
    op.create_index("ix_roi_assumptions_tenant_id", _AANNAMES, ["tenant_id"])

    if not _is_postgresql():
        return

    # Lus-idioom van 20260915_rls_resterende_tabellen.py: de architecture-guard lost `{tabel}` op
    # via de lus en ziet zo de tabelnaam in de SQL.
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
    # Laat alleen de twee eigen tabellen vallen; policy en indexen gaan met de tabel mee.
    op.drop_index("ix_roi_assumptions_tenant_id", table_name=_AANNAMES)
    op.drop_table(_AANNAMES)
    op.drop_index("ix_agent_run_metrics_tenant_id", table_name=_RUNS)
    op.drop_table(_RUNS)
