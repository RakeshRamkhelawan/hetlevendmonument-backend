"""Row Level Security voor de laatste 29 tabellen met een tenantkolom (ADR-036 OP-155).

Revision ID: 20260915_rls_rest
Revises: 20260915_bypass_rol
Create Date: 2026-09-15

Deze tabellen hebben WEL een `tenant_id` maar GEEN policy. Onder de niet-eigenaarrol
`sanskritisetu_app` (OP-151) zijn ze daarmee voor ELKE tenant volledig leesbaar -- het lek
dat de omschakeling juist moet dichten blijft dan open op 29 tabellen, waaronder `roles`,
`user_consents`, `dsar_requests`, `hitl_requests` en alle `governance_*`.

Gemeten 2026-09-15 op een verse database uit `alembic upgrade head` (PostgreSQL 15.19):
30 tabellen met een tenantkolom en zonder policy. `audit_logs` hoort daar BLIJVEND bij en
staat dus niet in deze migratie: die is bewust tenant-overstijgend en is ook in
`tenant_query_filter.py` uitgezonderd. Blijven over: 29.

**Prestaties: gemeten, niet aangenomen.** De vakliteratuur waarschuwt eensluidend dat
`current_setting()` niet leakproof is, de planner hem daarom niet in een index-conditie kan
duwen, en RLS tot honderd keer trager wordt. Dat zou betekenen dat deze 29 policies een
andere vorm nodig hadden. Gemeten op 400.000 rijen, als niet-eigenaar, met een query die
VOLLEDIG op de policy leunt:

    Bitmap Index Scan on ix_meting_rls_tenant
      Index Cond: (tenant_id = (NULLIF(current_setting('app.current_tenant', true), ''))::integer)
    Execution Time: 5.4 ms   (11 indexblokken)

De index WORDT gebruikt. De bestaande policyvorm blijft daarom ongewijzigd. Voorwaarde is
wel dat de tenantkolom LEIDEND in een index staat; gemeten voor alle 29: dat is zo (guard
`test_every_rls_table_has_a_leading_tenant_index`, OP-161).

**Twee kolomtypen, twee vormen.** `adaptation_rules`, `learning_insights` en
`learning_patterns` hebben `tenant_id VARCHAR(128)`, niet INTEGER. Die krijgen de variant
ZONDER `::INTEGER`; met de cast faalt de policy op elke rij. Gemeten dat die kolommen het
tenantnummer als TEKST bevatten: `src/core/learning/gdpr_service.py:226-232` schrijft en
leest daar consequent `str(tenant_id)`.

**Wat dit doet met SCHRIJVEN -- lees dit HELEMAAL voor je een schrijfpad beoordeelt.**

Een eerdere versie van deze docstring zei: "lezen faalt stil, schrijven faalt luid". Dat is
HALF waar, en de verkeerde helft droeg gewicht. Gemeten 2026-09-15 op deze policies, als
niet-eigenaar, zonder tenantcontext:

    SELECT  ->  0 rijen          STIL
    INSERT  ->  new row violates row-level security policy    LUID
    UPDATE  ->  UPDATE 0         STIL
    DELETE  ->  DELETE 0         STIL

De reden is dat `USING` twee verschillende rollen vervult. Bij INSERT wordt hij als
`WITH CHECK` op de NIEUWE rij toegepast -- die faalt dus luid. Bij UPDATE bepaalt `USING`
eerst WELKE RIJEN zichtbaar zijn om te wijzigen; zonder tenantcontext zijn dat er nul, dus
raakt het statement niets, is `rowcount` nul, slaagt de commit, en komt de `WITH CHECK`-kant
nooit aan bod. Bij DELETE geldt alleen `USING`.
(https://www.postgresql.org/docs/15/sql-createpolicy.html)

**Waarom dit ertoe doet.** De inventarisatie van schrijfpaden bij deze wijziging leunde op
de aanname dat een vergeten pad zichzelf zou melden bij de eerste start na de omschakeling.
Dat geldt alleen voor INSERT. Een vergeten UPDATE of DELETE verdwijnt in stilte: nul rijen,
geen fout, en een taak die "klaar" rapporteert. Twee zulke paden zijn bij de Gate 2-review
gevonden en gerepareerd (`retention_cleanup_job.py` en `learning/worker.py`), allebei
AVG-retentietaken die anders zouden hebben gemeld dat ze gedraaid hadden terwijl ze niets
verwijderden.

Elk pad dat in deze tabellen schrijft MOET dus een tenantcontext hebben, en bij UPDATE en
DELETE is er geen vangnet dat het je vertelt.

`roles` zit er bewust WEL in. `user_roles` heeft geen tenantkolom en kan dus zelf geen
policy krijgen (OP-190), maar de koppeling wordt door deze policy op `roles` alsnog
afgeschermd: een rol van een andere tenant is onzichtbaar, dus de join levert hem niet op.

De downgrade verwijdert precies wat deze migratie aanmaakt, per tabel, en zet RLS weer uit.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260915_rls_rest"
down_revision = "20260915_bypass_rol"
branch_labels = None
depends_on = None

# Gemeten 2026-09-15 uit `pg_class`/`pg_attribute` op een verse keten -- niet overgetypt.
_INTEGER_TABELLEN = (
    "activepieces_connections",
    "activepieces_flow_runs",
    "activepieces_flows",
    "activepieces_sync_logs",
    "agent_twin_consent_events",
    "ai_decisions",
    "collective_knowledge",
    "domain_packs",
    "dsar_requests",
    "employee_skills",
    "employee_trainings",
    "gatekeeper_decisions",
    "governance_accuracy_metrics",
    "governance_alerts",
    "governance_authority_reports",
    "governance_quality_checks",
    "governance_risk_entries",
    "hitl_requests",
    "role_required_skills",
    "roles",
    "skills",
    "tenant_llm_budget",
    "trainings",
    "twin_suggestion_log",
    "user_consents",
    "user_profiling_opt_outs",
)

# `tenant_id VARCHAR(128)`: de policy vergelijkt TEKST met TEKST, zonder cast.
_TEXT_TABELLEN = (
    "adaptation_rules",
    "learning_insights",
    "learning_patterns",
)

_INT_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
_TEXT_EXPRESSIE = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def _policynaam(tabel: str) -> str:
    return f"rls_{tabel}_tenant_isolation"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for tabel, expressie in [
        *[(t, _INT_EXPRESSIE) for t in _INTEGER_TABELLEN],
        *[(t, _TEXT_EXPRESSIE) for t in _TEXT_TABELLEN],
    ]:
        # `to_regclass`: een offline dry-run (`upgrade head --sql`) heeft de tabellen niet,
        # en `ALTER TABLE` op een ontbrekende tabel laat de hele keten omvallen. NOOIT
        # `sa.inspect(op.get_bind())` gebruiken -- dat crasht juist bij een offline run
        # (backend-patterns regel 9).
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
                        -- Dollar-quoting ($q$) en GEEN enkele quotes: de policy-expressie
                        -- bevat zelf `current_setting('app.current_tenant', true)`, en die
                        -- quotes zouden de EXECUTE-string vroegtijdig sluiten. Gemeten
                        -- 2026-09-15: dat gaf `syntax error at or near "."` en de migratie
                        -- faalde -- zichtbaar alleen als je de VOLLEDIGE uitvoer leest, niet
                        -- de laatste twee regels.
                        EXECUTE $q$CREATE POLICY {_policynaam(tabel)} ON {tabel} FOR ALL USING ({expressie})$q$;
                    END IF;
                END $$;
                """
            )
        )


def downgrade() -> None:
    if not _is_postgresql():
        return

    for tabel in (*_INTEGER_TABELLEN, *_TEXT_TABELLEN):
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('public.{tabel}') IS NULL THEN
                        RETURN;
                    END IF;
                    EXECUTE 'DROP POLICY IF EXISTS {_policynaam(tabel)} ON {tabel}';
                    EXECUTE 'ALTER TABLE {tabel} DISABLE ROW LEVEL SECURITY';
                END $$;
                """
            )
        )
