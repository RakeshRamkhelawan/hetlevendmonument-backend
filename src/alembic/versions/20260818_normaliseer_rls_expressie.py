"""Veertien RLS-policies gooien een fout in plaats van nul rijen te geven.

Revision ID: 20260818_rls_expr
Revises: 20260818_app_rol
Create Date: 2026-08-16

ADR-036 OP-151. `current_setting('app.current_tenant')` ZONDER tweede argument gooit
`unrecognized configuration parameter` als de instelling nooit is gezet, en `''::integer`
gooit `invalid input syntax for type integer` als hij leeg is. Beide gevallen komen voor:
de zestien engines buiten `db_manager` zetten geen tenantcontext (OP-153), en `SET LOCAL`
laat een lege waarde achter na een commit.

Gemeten 2026-08-16 op een verse database, als niet-eigenaar zonder tenantcontext:

    companies (deze vorm)                 InvalidTextRepresentation / UndefinedObject
    agents    (de veilige vorm)           0 rijen

Vandaag valt dat niet op omdat de applicatie als tabeleigenaar verbindt en PostgreSQL RLS
voor de eigenaar overslaat.

Veertien policies lopen stuk op een lege tenantcontext: elf gebruiken `current_setting`
zonder `missing_ok`, drie hebben dat wel maar missen de `NULLIF` en struikelen dus over
de LEGE waarde die `SET LOCAL` na een commit achterlaat. Dertien vergelijken op
`tenant_id`; `company_templates` is anders en wordt apart behandeld -- die tabel heeft
helemaal geen `tenant_id`-kolom (de kolom heet `contributed_by_tenant_id`) en een tweede,
bewust tenant-overstijgende policy voor platformsjablonen. Wie die eerste policy naar een
kale `tenant_id = ...` herschrijft, laat platformsjablonen voor iedereen verdwijnen.

Een lege tabel maakt dit NIET onschuldig: gemeten zijn `goals`, `departments`, `documents`
en `company_templates` alle vier leeg en geven alle vier toch de foutmelding. PostgreSQL
evalueert de policy-expressie ook als er geen rijen zijn.

De downgrade zet exact de oude vorm terug -- inclusief de fout, want dat is wat een inverse
betekent.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260818_rls_expr"
down_revision = "20260818_app_rol"
branch_labels = None
depends_on = None

# Tabel -> policynaam. Expliciet benoemd en niet gezocht: een guard die over een
# BENOEMDE verzameling loopt is in vijf seconden te controleren, en het mutatiebewijs
# heeft een regel per element (aanscherping 2026-08-14).
_OP_TENANT_ID: dict[str, str] = {
    "board_decisions": "board_decisions_tenant_isolation",
    "companies": "companies_tenant_isolation",
    "council_decisions": "tenant_isolation_council",
    "departments": "departments_tenant_isolation",
    "document_versions": "tenant_isolation_policy",
    "documents": "tenant_isolation_policy",
    "external_agents": "external_agents_tenant_isolation",
    "goals": "goals_tenant_isolation",
    "officer_verdicts": "tenant_isolation_officer_verdicts",
    "pack_activation_audit_logs": "pack_activation_audit_tenant_isolation",
    # De drie hieronder hebben WEL `missing_ok` maar GEEN `NULLIF`. Ze werden bij de eerste
    # meting als veilig geteld omdat die op de tekst `, true)` zocht -- de terugkerende
    # fout: de zoektocht vindt het woord en niet het gedrag. Ze crashen niet op een
    # ontbrekende instelling, maar wel op een LEGE, en leeg is precies wat `SET LOCAL`
    # achterlaat na een commit. Betrapt door
    # `test_no_policy_raises_when_the_tenant_context_is_missing`, niet door de meting.
    "agent_configs": "tenant_isolation",
    "ai_act_incident_reports": "tenant_isolation",
    "model_provenance_records": "tenant_isolation",
}

_VEILIG = "NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
_ONVEILIG = "current_setting('app.current_tenant')::INTEGER"
# De drie tussenvorm-tabellen krijgen bij een downgrade hun EIGEN oude vorm terug, niet de
# vorm van de andere elf -- anders is de downgrade geen inverse maar een andere fout.
_TUSSENVORM = "current_setting('app.current_tenant', true)::INTEGER"
_TUSSENVORM_TABELLEN = frozenset(
    {"agent_configs", "ai_act_incident_reports", "model_provenance_records"}
)

# De veertiende: andere kolom, en een OR-tak voor platformsjablonen die moet blijven staan.
_SJABLONEN_TABEL = "company_templates"
_SJABLONEN_POLICY = "company_templates_tenant_isolation"
_SJABLONEN_KOLOM = "contributed_by_tenant_id"


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def _zet_policies(expressie: str, *, terug: bool = False) -> None:
    for tabel, policy in _OP_TENANT_ID.items():
        vorm = _TUSSENVORM if (terug and tabel in _TUSSENVORM_TABELLEN) else expressie
        op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {tabel}"))
        op.execute(sa.text(f"CREATE POLICY {policy} ON {tabel} FOR ALL USING (tenant_id = {vorm})"))

    op.execute(sa.text(f"DROP POLICY IF EXISTS {_SJABLONEN_POLICY} ON {_SJABLONEN_TABEL}"))
    op.execute(
        sa.text(
            f"CREATE POLICY {_SJABLONEN_POLICY} ON {_SJABLONEN_TABEL} FOR ALL USING ("
            f"is_platform_template = true OR {_SJABLONEN_KOLOM} = {expressie})"
        )
    )


def upgrade() -> None:
    if not _is_postgresql():
        return
    _zet_policies(_VEILIG)


def downgrade() -> None:
    """Exacte inverse: elke policy terug in de vorm die hij VOOR deze migratie had."""
    if not _is_postgresql():
        return
    _zet_policies(_ONVEILIG, terug=True)
