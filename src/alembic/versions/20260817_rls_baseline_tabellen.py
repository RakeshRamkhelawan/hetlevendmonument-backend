"""RLS voor de tabellen uit de baseline (ADR-005, ADR-036 OP-140)

`20260817_baseline_tabellen` maakt 71 tabellen aan maar zette geen Row Level Security. Dat
wijkt af van de vaste conventie in deze repo -- 41 andere tabel-aanmakende migraties doen dat
wel -- en ADR-005 noemt RLS expliciet als de laatste verdedigingslinie.

**WEES PRECIES OVER WAT DIT VANDAAG OPLEVERT (gemeten 2026-08-17, Gate 2-review).** RLS
geldt in PostgreSQL NIET voor de eigenaar van de tabel en niet voor een superuser, en
`FORCE ROW LEVEL SECURITY` helpt evenmin tegen een superuser. Deze applicatie verbindt
vandaag als `postgres` -- de eigenaar (`.env.example`, `docker-compose.yml`) -- en er
bestaat geen aparte applicatierol. Gemeten met exact deze policy-vorm: als eigenaar 2 van
2 rijen zichtbaar, als niet-eigenaar 1 van 2, en zonder tenantcontext 0.

De policies zijn dus correct en werken zodra de applicatie met een niet-eigenaar-rol
verbindt; tot dat moment beschermen ze niet tegen een lek in de applicatiecode. Dat is
geen reden om ze niet te zetten -- ze horen bij het schema, en de 41 bestaande
RLS-migraties hebben exact dezelfde beperking -- maar het is wel iets anders dan wat een
eerdere versie van deze tekst beweerde. De ontbrekende applicatierol staat als OP-151 in
ADR-036. Gevonden door de Gate 2-security-review op commit 201520ca.

Waarom dit ertoe doet op precies dit moment: de baseline legt het schema vast van ELKE
toekomstige omgeving. Zonder deze migratie krijgt elke nieuwe klantomgeving 69 tenant-
gescheiden tabellen zonder die laatste laag, waaronder `scheduling_calendar_integrations`
(versleutelde OAuth-tokens naar Google/Outlook), `user_sessions` (sessietokens, IP, user
agent), `security_alerts` (bron-IP en getroffen resources) en `cva_conversations`
(gespreksinhoud).

TWEE VARIANTEN, en dat is geen detail. De bestaande policy-vorm uit
`20260522_add_rls_core_tables.py` cast de tenantcontext naar INTEGER. Drie analytics-tabellen
hebben `tenant_id VARCHAR` (`src/core/analytics/models.py`); daar geeft die cast een typefout
bij elke query. Die krijgen een ::TEXT-variant.

GEMETEN 2026-08-17, want het is niet vanzelfsprekend: `FOR ALL USING (...)` ZONDER
`WITH CHECK` beperkt ook het SCHRIJVEN. PostgreSQL valt voor INSERT terug op de
`USING`-expressie wanneer `WITH CHECK` ontbreekt. Aangetoond met een rol die geen
eigenaar en geen superuser is (die omzeilen RLS sowieso): met `app.current_tenant = '1'`
slaagt een insert met `tenant_id = 1`, wordt een insert met `tenant_id = 2` geweigerd
(`InsufficientPrivilege`), en ziet die sessie uitsluitend zijn eigen rij.

`missing_ok=true` in `current_setting`: zonder tenantcontext levert de policy NULL en dus nul
rijen, in plaats van een fout. Dat is dezelfde fail-secure keuze als in de bestaande migratie.

Idempotent met `DROP POLICY IF EXISTS` ervoor, zodat hij ook draait op een database waar een
policy met dezelfde naam al bestaat.

Revision ID: 20260817_rls_baseline
Revises: 20260817_baseline_tabellen
Create Date: 2026-08-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_rls_baseline"
down_revision: str | Sequence[str] | None = "20260817_baseline_tabellen"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# tenant_id is INTEGER -- de standaardvorm.
_INT_TABELLEN: tuple[str, ...] = (
    "ab_tests",
    "agent_memory_profiles",
    "agent_profile_snapshots",
    "agent_synapses",
    "aiqualityevents",
    "availability_patterns",
    "badges",
    "billing_events",
    "budget_usage",
    "c7_workflow_snapshots",
    "campaign_analytics",
    "campaign_segments",
    "comments",
    "cva_conversations",
    "dead_letter_entries",
    "deletion_audit",
    "email_campaigns",
    "email_templates",
    "entity_tags",
    "evaluation_results",
    "evaluation_runs",
    "immune_antibodies",
    "immune_memory_cells",
    "knowledge_entries",
    "learning_experiences",
    "memory_consolidation_runs",
    "memory_items",
    "memory_retrieval_traces",
    "notifications",
    "organism_registry",
    "point_transactions",
    "procedure_executions",
    "procedure_metadata",
    "role_permissions",
    "scheduling_calendar_events",
    "scheduling_calendar_integrations",
    "scheduling_constraints",
    "scheduling_design_partners",
    "scheduling_preferences",
    "scheduling_sync_conflicts",
    "scheduling_time_blocks",
    "scheduling_webhook_registrations",
    "security_alerts",
    "session_memory_events",
    "signal_audit_log",
    "signal_cooldowns",
    "strategic_insights",
    "strategic_objectives",
    "strategies",
    "tags",
    "tenant_custom_data",
    "tenant_integrations",
    "usage_records",
    "user_badges",
    "user_email_preferences",
    "user_points",
    "user_scheduling_profiles",
    "user_sessions",
    "webhook_deliveries",
    "webhook_endpoints",
    "workflow_change_logs",
    "workflow_executions",
    "workflow_experiences",
    "workflow_instances",
    "workflow_templates",
    "workflow_versions",
)

# tenant_id is VARCHAR (src/core/analytics/models.py) -- cast naar TEXT.
_TEXT_TABELLEN: tuple[str, ...] = (
    "analytics_events",
    "analytics_metrics",
    "analytics_sessions",
)

# Geen tenant_id: hangen via een FK aan een tenant-gescheiden ouder.
# `token_blacklist` -> users.id, `scheduling_partner_feedback` ->
# scheduling_design_partners.id.
_ZONDER_TENANT: tuple[str, ...] = (
    "scheduling_partner_feedback",
    "token_blacklist",
)


def _is_postgresql() -> bool:
    """RLS bestaat niet in SQLite; de unit-tests draaien daarop."""
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    for tbl in _INT_TABELLEN:
        op.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS base_{tbl}_tenant_isolation ON {tbl}"))
        op.execute(
            sa.text(
                f"CREATE POLICY base_{tbl}_tenant_isolation ON {tbl} "
                f"FOR ALL USING ("
                f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::INTEGER"
                f")"
            )
        )

    for tbl in _TEXT_TABELLEN:
        op.execute(sa.text(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"DROP POLICY IF EXISTS base_{tbl}_tenant_isolation ON {tbl}"))
        op.execute(
            sa.text(
                f"CREATE POLICY base_{tbl}_tenant_isolation ON {tbl} "
                f"FOR ALL USING ("
                f"tenant_id = NULLIF(current_setting('app.current_tenant', true), '')"
                f")"
            )
        )


def downgrade() -> None:
    """Policies weghalen en RLS uitzetten -- exacte inverse."""
    if not _is_postgresql():
        return

    for tbl in _INT_TABELLEN + _TEXT_TABELLEN:
        op.execute(sa.text(f"DROP POLICY IF EXISTS base_{tbl}_tenant_isolation ON {tbl}"))
        op.execute(sa.text(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY"))
