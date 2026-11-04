"""baseline: de 71 tabellen die de keten niet aanmaakte (ADR-036 OP-140)

Gemeten 2026-08-17 op een VERSE PostgreSQL na `alembic upgrade head`: 120 tabellen, terwijl de
applicatie er 186 verwacht. Eenenzeventig modeltabellen werden door geen enkele migratie
aangemaakt, waaronder `notifications`, `token_blacklist` (inloggen), `workflow_executions`,
`deletion_audit` (AVG-verwijderingen), `role_permissions` en `dead_letter_entries`. Een NIEUWE
omgeving -- nieuwe klant, tweede regio, herstel na een calamiteit -- was daardoor niet uit de
migraties te bouwen.

OORZAAK, een laag dieper: `src/alembic/env.py` gebruikte de kleinste van twee
modelregistraties, waardoor 43 modellen voor `--autogenerate` onzichtbaar waren en dus nooit
een migratie kregen (OP-147). Dezelfde blinde vlek liet ooit `tenants.prana_budget` vallen.

De DDL is gecompileerd uit `Base.metadata` en is dus per constructie gelijk aan wat de modellen
declareren. Tabellen staan in afhankelijkheidsvolgorde; ENUM-typen gaan vooraf.

DRIE EIGENSCHAPPEN DIE ER LOS VAN ELKAAR TOE DOEN
-------------------------------------------------

1. **Uitsluitend TOEVOEGEND.** De autogenerate-uitvoer bevatte daarnaast 11
   kolomverwijderingen, 28 constraintverwijderingen, 52 indexverwijderingen en 155
   kolomwijzigingen -- waaronder `users.first_name`, `users.last_name`, `roles.permissions` en
   `tenants.config`. Dat is dataverlies en een productbeslissing; bewust weggelaten en
   vastgelegd als OP-150.

2. **De vorm convergeert voor de indexen (Gate 2-review, HIGH-2).** `CREATE TABLE IF NOT
   EXISTS` slaat een bestaande tabel over, maar `CREATE INDEX ... ON tabel (kolom)` is alleen
   voorwaardelijk op de INDEXNAAM. Een bestaande tabel met een kolom minder liet de hele
   migratie AFBREKEN -- gereproduceerd op de testdatabase van dit project zelf, waar
   `email_campaigns` de kolom `status` mist. Daarom staat er per kolom een
   `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` tussen de tabel en zijn indexen. Uitsluitend
   toevoegend; een kolom die het model niet meer kent blijft staan.

3. **De downgrade is een ECHTE inverse (Gate 2-review, HIGH-1).** De vorige versie dropte
   onvoorwaardelijk alle 71 tabellen, ook op een database waar de upgrade ze niet had
   aangemaakt -- daar was `alembic downgrade -1` een `DROP` van 71 tabellen MET data,
   waaronder `deletion_audit`, `billing_events` en `usage_records`. De upgrade noteert nu
   VOORAF in `_baseline_20260817_created` welke van de 71 nog niet bestonden; de downgrade ruimt
   uitsluitend die op en verwijdert daarna zijn eigen boekhouding.

Bewust GEEN `sa.inspect(op.get_bind())`: dat crasht bij een offline dry-run, en juist die
uitweg heeft OP-148 veroorzaakt. Alle voorwaardelijkheid zit in SQL die offline gewoon
meeschrijft.

Revision ID: 20260817_baseline_tabellen
Revises: 20260815_tenant_prana_budget
Create Date: 2026-08-17

"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260817_baseline_tabellen"
down_revision: str | Sequence[str] | None = "20260815_tenant_prana_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Afhankelijkheidsvolgorde uit `Base.metadata.sorted_tables`.
_TABELLEN: tuple[str, ...] = (

    "analytics_events",
    "analytics_metrics",
    "analytics_sessions",
    "procedure_executions",
    "procedure_metadata",
    "agent_synapses",
    "aiqualityevents",
    "availability_patterns",
    "badges",
    "billing_events",
    "budget_usage",
    "c7_workflow_snapshots",
    "cva_conversations",
    "email_templates",
    "evaluation_runs",
    "immune_memory_cells",
    "knowledge_entries",
    "learning_experiences",
    "memory_consolidation_runs",
    "organism_registry",
    "scheduling_calendar_events",
    "scheduling_calendar_integrations",
    "scheduling_constraints",
    "scheduling_design_partners",
    "scheduling_preferences",
    "scheduling_time_blocks",
    "signal_audit_log",
    "signal_cooldowns",
    "strategic_insights",
    "strategic_objectives",
    "strategies",
    "tags",
    "tenant_custom_data",
    "tenant_integrations",
    "user_scheduling_profiles",
    "user_sessions",
    "webhook_endpoints",
    "workflow_experiences",
    "agent_memory_profiles",
    "comments",
    "dead_letter_entries",
    "deletion_audit",
    "email_campaigns",
    "entity_tags",
    "evaluation_results",
    "immune_antibodies",
    "memory_items",
    "memory_retrieval_traces",
    "notifications",
    "point_transactions",
    "role_permissions",
    "scheduling_partner_feedback",
    "scheduling_sync_conflicts",
    "scheduling_webhook_registrations",
    "security_alerts",
    "token_blacklist",
    "usage_records",
    "user_badges",
    "user_email_preferences",
    "user_points",
    "webhook_deliveries",
    "workflow_templates",
    "workflow_versions",
    "ab_tests",
    "agent_profile_snapshots",
    "campaign_analytics",
    "campaign_segments",
    "session_memory_events",
    "workflow_change_logs",
    "workflow_instances",
    "workflow_executions",
)

# ENUM-typen die deze tabellen gebruiken.
_ENUMS: tuple[str, ...] = (
    "campaignstatus",
    "executionstatus",
    "workflowstatus",
)

_BOEKHOUDING = "_baseline_20260817_created"


def upgrade() -> None:
    """Maakt alleen aan wat er nog niet is; veilig op een bestaande database."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS _baseline_20260817_created (
            tabel TEXT PRIMARY KEY
        )
        """
    )
    op.execute(
        """
        INSERT INTO _baseline_20260817_created (tabel)
        SELECT t FROM unnest(ARRAY['analytics_events', 'analytics_metrics', 'analytics_sessions', 'procedure_executions', 'procedure_metadata', 'agent_synapses', 'aiqualityevents', 'availability_patterns', 'badges', 'billing_events', 'budget_usage', 'c7_workflow_snapshots', 'cva_conversations', 'email_templates', 'evaluation_runs', 'immune_memory_cells', 'knowledge_entries', 'learning_experiences', 'memory_consolidation_runs', 'organism_registry', 'scheduling_calendar_events', 'scheduling_calendar_integrations', 'scheduling_constraints', 'scheduling_design_partners', 'scheduling_preferences', 'scheduling_time_blocks', 'signal_audit_log', 'signal_cooldowns', 'strategic_insights', 'strategic_objectives', 'strategies', 'tags', 'tenant_custom_data', 'tenant_integrations', 'user_scheduling_profiles', 'user_sessions', 'webhook_endpoints', 'workflow_experiences', 'agent_memory_profiles', 'comments', 'dead_letter_entries', 'deletion_audit', 'email_campaigns', 'entity_tags', 'evaluation_results', 'immune_antibodies', 'memory_items', 'memory_retrieval_traces', 'notifications', 'point_transactions', 'role_permissions', 'scheduling_partner_feedback', 'scheduling_sync_conflicts', 'scheduling_webhook_registrations', 'security_alerts', 'token_blacklist', 'usage_records', 'user_badges', 'user_email_preferences', 'user_points', 'webhook_deliveries', 'workflow_templates', 'workflow_versions', 'ab_tests', 'agent_profile_snapshots', 'campaign_analytics', 'campaign_segments', 'session_memory_events', 'workflow_change_logs', 'workflow_instances', 'workflow_executions']) AS t
        WHERE to_regclass('public.' || t) IS NULL
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            bestaand text;
            gewenst  text;
        BEGIN
            CREATE TYPE campaignstatus AS ENUM ('draft', 'scheduled', 'sending', 'sent', 'paused', 'failed');
        EXCEPTION WHEN duplicate_object THEN
            -- ADR-036 OP-152: `THEN NULL` accepteerde OOK een bestaand type met
            -- ANDERE waarden. De migratie meldde dan succes en het schema week af
            -- van het model; de eerste INSERT met een waarde die er niet in staat
            -- faalt pas maanden later, ver van de oorzaak. Vergelijken en melden.
            SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
              INTO bestaand
              FROM pg_enum e
              JOIN pg_type ty ON ty.oid = e.enumtypid
             WHERE ty.typname = 'campaignstatus';
            gewenst := array_to_string(ARRAY['draft', 'scheduled', 'sending', 'sent', 'paused', 'failed'], ',');
            IF bestaand IS DISTINCT FROM gewenst THEN
                RAISE WARNING 'WAARSCHUWING (ADR-036 OP-152): type campaignstatus bestond al met andere waarden. Aanwezig: %. Verwacht: %. Het schema wijkt af van het model.', bestaand, gewenst;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            bestaand text;
            gewenst  text;
        BEGIN
            CREATE TYPE executionstatus AS ENUM ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'PAUSED');
        EXCEPTION WHEN duplicate_object THEN
            -- ADR-036 OP-152: `THEN NULL` accepteerde OOK een bestaand type met
            -- ANDERE waarden. De migratie meldde dan succes en het schema week af
            -- van het model; de eerste INSERT met een waarde die er niet in staat
            -- faalt pas maanden later, ver van de oorzaak. Vergelijken en melden.
            SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
              INTO bestaand
              FROM pg_enum e
              JOIN pg_type ty ON ty.oid = e.enumtypid
             WHERE ty.typname = 'executionstatus';
            gewenst := array_to_string(ARRAY['PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'PAUSED'], ',');
            IF bestaand IS DISTINCT FROM gewenst THEN
                RAISE WARNING 'WAARSCHUWING (ADR-036 OP-152): type executionstatus bestond al met andere waarden. Aanwezig: %. Verwacht: %. Het schema wijkt af van het model.', bestaand, gewenst;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        DECLARE
            bestaand text;
            gewenst  text;
        BEGIN
            CREATE TYPE workflowstatus AS ENUM ('DRAFT', 'ACTIVE', 'ARCHIVED');
        EXCEPTION WHEN duplicate_object THEN
            -- ADR-036 OP-152: `THEN NULL` accepteerde OOK een bestaand type met
            -- ANDERE waarden. De migratie meldde dan succes en het schema week af
            -- van het model; de eerste INSERT met een waarde die er niet in staat
            -- faalt pas maanden later, ver van de oorzaak. Vergelijken en melden.
            SELECT string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
              INTO bestaand
              FROM pg_enum e
              JOIN pg_type ty ON ty.oid = e.enumtypid
             WHERE ty.typname = 'workflowstatus';
            gewenst := array_to_string(ARRAY['DRAFT', 'ACTIVE', 'ARCHIVED'], ',');
            IF bestaand IS DISTINCT FROM gewenst THEN
                RAISE WARNING 'WAARSCHUWING (ADR-036 OP-152): type workflowstatus bestond al met andere waarden. Aanwezig: %. Verwacht: %. Het schema wijkt af van het model.', bestaand, gewenst;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_events (
        	id SERIAL NOT NULL, 
        	tenant_id VARCHAR NOT NULL, 
        	session_id VARCHAR NOT NULL, 
        	user_id VARCHAR, 
        	event_type VARCHAR(50) NOT NULL, 
        	event_subtype VARCHAR(100), 
        	severity VARCHAR(20) NOT NULL, 
        	event_data JSON NOT NULL, 
        	context JSON, 
        	event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	batch_id VARCHAR, 
        	is_deleted BOOLEAN NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_metrics (
        	id SERIAL NOT NULL, 
        	tenant_id VARCHAR NOT NULL, 
        	metric_type VARCHAR(100) NOT NULL, 
        	metric_name VARCHAR(100) NOT NULL, 
        	aggregation_level VARCHAR(20) NOT NULL, 
        	time_bucket TIMESTAMP WITH TIME ZONE NOT NULL, 
        	value_count INTEGER NOT NULL, 
        	value_sum FLOAT NOT NULL, 
        	value_min FLOAT, 
        	value_max FLOAT, 
        	value_avg FLOAT, 
        	value_p50 FLOAT, 
        	value_p95 FLOAT, 
        	value_p99 FLOAT, 
        	dimensions JSON, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analytics_sessions (
        	id SERIAL NOT NULL, 
        	tenant_id VARCHAR NOT NULL, 
        	session_id VARCHAR NOT NULL, 
        	user_id VARCHAR, 
        	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
        	end_time TIMESTAMP WITH TIME ZONE, 
        	duration_seconds INTEGER, 
        	page_view_count INTEGER NOT NULL, 
        	event_count INTEGER NOT NULL, 
        	error_count INTEGER NOT NULL, 
        	actions JSON, 
        	device_type VARCHAR(50), 
        	browser VARCHAR(100), 
        	os VARCHAR(100), 
        	is_active BOOLEAN NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS procedure_executions (
        	id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	procedure_id UUID NOT NULL, 
        	status VARCHAR(50) NOT NULL, 
        	error_message VARCHAR(2000), 
        	audit_trail JSONB NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	started_at TIMESTAMP WITH TIME ZONE, 
        	completed_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS procedure_metadata (
        	id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	flow_id UUID NOT NULL, 
        	domain_pack_id UUID NOT NULL, 
        	category VARCHAR(255) NOT NULL, 
        	description VARCHAR(2000), 
        	intent_tags VARCHAR[] NOT NULL, 
        	prerequisites VARCHAR[] NOT NULL, 
        	estimated_duration_minutes INTEGER, 
        	is_platform_template BOOLEAN NOT NULL, 
        	procedure_metadata JSONB NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_synapses (
        	tenant_id INTEGER NOT NULL, 
        	agent_a VARCHAR NOT NULL, 
        	agent_b VARCHAR NOT NULL, 
        	connection_strength FLOAT, 
        	last_communication TIMESTAMP WITH TIME ZONE, 
        	communication_count INTEGER, 
        	successful_collaborations INTEGER, 
        	failed_collaborations INTEGER, 
        	PRIMARY KEY (tenant_id, agent_a, agent_b), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aiqualityevents (
        	id UUID NOT NULL, 
        	execution_id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	event_type VARCHAR(50) NOT NULL, 
        	severity VARCHAR(20) NOT NULL, 
        	details JSONB NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS availability_patterns (
        	id UUID NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	day_of_week INTEGER NOT NULL, 
        	hour_block INTEGER NOT NULL, 
        	total_slots INTEGER NOT NULL, 
        	busy_slots INTEGER NOT NULL, 
        	free_slots INTEGER NOT NULL, 
        	tentative_slots INTEGER NOT NULL, 
        	availability_score FLOAT NOT NULL, 
        	confidence FLOAT NOT NULL, 
        	sample_weeks INTEGER NOT NULL, 
        	last_updated TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_availability_pattern UNIQUE (user_id, tenant_id, day_of_week, hour_block), 
        	CONSTRAINT chk_day_of_week CHECK (day_of_week >= 0 AND day_of_week <= 6), 
        	CONSTRAINT chk_hour_block CHECK (hour_block >= 0 AND hour_block <= 23), 
        	CONSTRAINT chk_availability_score CHECK (availability_score >= 0.0 AND availability_score <= 1.0), 
        	CONSTRAINT chk_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS badges (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	code VARCHAR(50) NOT NULL, 
        	name VARCHAR(100) NOT NULL, 
        	description TEXT, 
        	icon VARCHAR(50), 
        	color VARCHAR(20), 
        	points_required INTEGER, 
        	is_secret BOOLEAN, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS billing_events (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	event_type VARCHAR(50) NOT NULL, 
        	amount_cents INTEGER, 
        	currency VARCHAR(3) DEFAULT 'EUR' NOT NULL, 
        	description TEXT, 
        	external_ref VARCHAR(255), 
        	metadata JSON, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS budget_usage (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100) NOT NULL, 
        	tokens_used INTEGER, 
        	cost_usd NUMERIC(10, 4), 
        	period_start TIMESTAMP WITH TIME ZONE NOT NULL, 
        	period_end TIMESTAMP WITH TIME ZONE NOT NULL, 
        	model_name VARCHAR(50), 
        	task_count INTEGER, 
        	created_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS c7_workflow_snapshots (
        	id SERIAL NOT NULL, 
        	workflow_id VARCHAR(50) NOT NULL, 
        	content BYTEA NOT NULL, 
        	size_bytes INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	created_by INTEGER, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cva_conversations (
        	id VARCHAR(50) NOT NULL, 
        	session_id VARCHAR(50) NOT NULL, 
        	user_id VARCHAR(100) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_message TEXT NOT NULL, 
        	cva_response TEXT NOT NULL, 
        	response_metadata JSONB, 
        	performance_data JSONB, 
        	conversation_turn INTEGER NOT NULL, 
        	context_summary TEXT, 
        	user_feedback VARCHAR(20), 
        	feedback_details TEXT, 
        	attached_files JSONB, 
        	conversation_topic VARCHAR(200), 
        	conversation_category VARCHAR(100), 
        	keywords JSONB, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_templates (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	name VARCHAR(255) NOT NULL, 
        	subject_template VARCHAR(255) NOT NULL, 
        	content_template TEXT NOT NULL, 
        	description TEXT, 
        	category VARCHAR(50), 
        	is_public BOOLEAN DEFAULT 'false' NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_runs (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	name VARCHAR(255), 
        	num_samples INTEGER, 
        	status VARCHAR(50), 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	started_at TIMESTAMP WITH TIME ZONE, 
        	completed_at TIMESTAMP WITH TIME ZONE, 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	avg_faithfulness FLOAT, 
        	avg_precision FLOAT, 
        	avg_recall FLOAT, 
        	avg_context_precision FLOAT, 
        	avg_answer_relevancy FLOAT, 
        	avg_context_recall FLOAT, 
        	error TEXT, 
        	metadata JSON, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS immune_memory_cells (
        	id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	threat_signature VARCHAR NOT NULL, 
        	threat_type VARCHAR NOT NULL, 
        	threat_description TEXT, 
        	antibodies_used JSONB NOT NULL, 
        	outcome JSONB, 
        	lessons_learned JSONB, 
        	reinforced_count INTEGER, 
        	effectiveness_score FLOAT, 
        	created_at TIMESTAMP WITH TIME ZONE, 
        	last_reinforced TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_entries (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	content TEXT NOT NULL, 
        	type VARCHAR(100) NOT NULL, 
        	entry_metadata JSONB, 
        	confidence_score FLOAT NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_experiences (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	event_id VARCHAR(255) NOT NULL, 
        	event_type VARCHAR(100) NOT NULL, 
        	agent_id VARCHAR(255), 
        	task_type VARCHAR(100), 
        	success BOOLEAN, 
        	duration FLOAT, 
        	context JSONB, 
        	metrics JSONB, 
        	user_id VARCHAR(255), 
        	session_id VARCHAR(255), 
        	confidence FLOAT NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_consolidation_runs (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100), 
        	started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	completed_at TIMESTAMP WITH TIME ZONE, 
        	status VARCHAR(20) NOT NULL, 
        	sessions_processed INTEGER NOT NULL, 
        	events_processed INTEGER NOT NULL, 
        	items_created INTEGER NOT NULL, 
        	items_archived INTEGER NOT NULL, 
        	contradictions_found INTEGER NOT NULL, 
        	error_message TEXT, 
        	run_metadata JSON NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organism_registry (
        	id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	agent_id VARCHAR NOT NULL, 
        	agent_type VARCHAR NOT NULL, 
        	department VARCHAR NOT NULL, 
        	registered_at TIMESTAMP WITH TIME ZONE, 
        	last_heartbeat TIMESTAMP WITH TIME ZONE, 
        	workload JSONB, 
        	emotional_state JSONB, 
        	status VARCHAR, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_calendar_events (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	title VARCHAR(255) NOT NULL, 
        	description TEXT, 
        	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
        	end_time TIMESTAMP WITH TIME ZONE NOT NULL, 
        	location VARCHAR(500), 
        	organizer_id VARCHAR(255) NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	participants JSON, 
        	event_type VARCHAR(50) NOT NULL, 
        	status VARCHAR(50) NOT NULL, 
        	priority INTEGER NOT NULL, 
        	recurrence_rule VARCHAR(500), 
        	metadata_json JSON, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	is_deleted BOOLEAN NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_calendar_integrations (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	provider VARCHAR(50) NOT NULL, 
        	provider_account_id VARCHAR(255) NOT NULL, 
        	provider_calendar_id VARCHAR(255) NOT NULL, 
        	access_token_encrypted TEXT NOT NULL, 
        	refresh_token_encrypted TEXT, 
        	token_expires_at TIMESTAMP WITH TIME ZONE, 
        	token_scope VARCHAR(500), 
        	is_active BOOLEAN NOT NULL, 
        	last_synced_at TIMESTAMP WITH TIME ZONE, 
        	sync_token VARCHAR(500), 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	is_deleted BOOLEAN NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_calendar_integration_user_provider UNIQUE (tenant_id, user_id, provider), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_constraints (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	constraint_type VARCHAR(50) NOT NULL, 
        	is_hard BOOLEAN NOT NULL, 
        	parameters JSON, 
        	description TEXT, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	is_deleted BOOLEAN NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_design_partners (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	name VARCHAR(255) NOT NULL, 
        	industry VARCHAR(50) NOT NULL, 
        	contact_email VARCHAR(255) NOT NULL, 
        	contact_name VARCHAR(255), 
        	status VARCHAR(20) NOT NULL, 
        	start_date TIMESTAMP WITH TIME ZONE NOT NULL, 
        	end_date TIMESTAMP WITH TIME ZONE NOT NULL, 
        	max_users INTEGER NOT NULL, 
        	allowed_features JSON NOT NULL, 
        	total_events_created INTEGER NOT NULL, 
        	total_conflicts_detected INTEGER NOT NULL, 
        	api_calls_count INTEGER NOT NULL, 
        	error_count INTEGER NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_preferences (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	timezone_name VARCHAR(100) NOT NULL, 
        	working_hours_start TIME WITHOUT TIME ZONE, 
        	working_hours_end TIME WITHOUT TIME ZONE, 
        	preferred_duration_minutes INTEGER NOT NULL, 
        	buffer_minutes INTEGER NOT NULL, 
        	preferences_json JSON, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	is_deleted BOOLEAN NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_scheduling_pref_tenant_user UNIQUE (tenant_id, user_id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_time_blocks (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	block_type VARCHAR(50) NOT NULL, 
        	start_time TIMESTAMP WITH TIME ZONE NOT NULL, 
        	end_time TIMESTAMP WITH TIME ZONE NOT NULL, 
        	recurrence_rule VARCHAR(500), 
        	is_hard_block BOOLEAN NOT NULL, 
        	label VARCHAR(255), 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	is_deleted BOOLEAN NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_audit_log (
        	id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	signal_id VARCHAR NOT NULL, 
        	source_agent VARCHAR NOT NULL, 
        	target_agents JSONB, 
        	tier VARCHAR NOT NULL, 
        	payload_hash VARCHAR(64), 
        	payload_size_bytes INTEGER, 
        	processed_at TIMESTAMP WITH TIME ZONE, 
        	processing_latency_ms INTEGER, 
        	antibody_triggered VARCHAR, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS signal_cooldowns (
        	tenant_id INTEGER NOT NULL, 
        	signal_type VARCHAR NOT NULL, 
        	sender VARCHAR NOT NULL, 
        	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (tenant_id, signal_type, sender), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategic_insights (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	insight_id VARCHAR(255) NOT NULL, 
        	strategy_type VARCHAR(100) NOT NULL, 
        	title VARCHAR(500) NOT NULL, 
        	description TEXT NOT NULL, 
        	confidence FLOAT NOT NULL, 
        	impact_score FLOAT NOT NULL, 
        	urgency_score FLOAT NOT NULL, 
        	supporting_evidence JSONB, 
        	recommended_actions JSONB, 
        	risks JSONB, 
        	opportunities JSONB, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategic_objectives (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	objective_id VARCHAR(255) NOT NULL, 
        	title VARCHAR(500) NOT NULL, 
        	description TEXT, 
        	priority INTEGER NOT NULL, 
        	status VARCHAR(50) NOT NULL, 
        	progress FLOAT NOT NULL, 
        	success_criteria JSONB, 
        	key_results JSONB, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS strategies (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	strategy_id VARCHAR(255) NOT NULL, 
        	strategy_type VARCHAR(100) NOT NULL, 
        	status VARCHAR(50) NOT NULL, 
        	analysis JSONB, 
        	recommendations JSONB, 
        	implementation_plan JSONB, 
        	success_metrics JSONB, 
        	confidence_score FLOAT NOT NULL, 
        	context_data JSONB, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tags (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	name VARCHAR(100) NOT NULL, 
        	color VARCHAR(7), 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_tags_tenant_name UNIQUE (tenant_id, name), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_custom_data (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	namespace VARCHAR(100) NOT NULL, 
        	key VARCHAR(255) NOT NULL, 
        	value JSON NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_tenant_custom_data UNIQUE (tenant_id, namespace, key), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_integrations (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	channel_type VARCHAR(50) NOT NULL, 
        	bot_token VARCHAR(255), 
        	webhook_secret VARCHAR(255), 
        	provider_config JSON, 
        	is_active BOOLEAN NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_scheduling_profiles (
        	id UUID NOT NULL, 
        	user_id VARCHAR(255) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	chronotype VARCHAR(20) NOT NULL, 
        	preferred_morning_start TIME WITH TIME ZONE, 
        	preferred_morning_end TIME WITH TIME ZONE, 
        	preferred_afternoon_start TIME WITH TIME ZONE, 
        	preferred_afternoon_end TIME WITH TIME ZONE, 
        	focus_time_min_duration INTEGER NOT NULL, 
        	protect_focus_time BOOLEAN NOT NULL, 
        	default_prep_buffer INTEGER NOT NULL, 
        	default_recovery_buffer INTEGER NOT NULL, 
        	travel_buffer_minutes INTEGER NOT NULL, 
        	max_meetings_per_day INTEGER NOT NULL, 
        	max_consecutive_meetings INTEGER NOT NULL, 
        	timezone VARCHAR(50) NOT NULL, 
        	last_pattern_analysis TIMESTAMP WITHOUT TIME ZONE, 
        	pattern_confidence FLOAT NOT NULL, 
        	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT chk_focus_duration_range CHECK (focus_time_min_duration >= 30 AND focus_time_min_duration <= 480), 
        	CONSTRAINT chk_meetings_range CHECK (max_meetings_per_day >= 1 AND max_meetings_per_day <= 20), 
        	CONSTRAINT chk_consecutive_range CHECK (max_consecutive_meetings >= 1 AND max_consecutive_meetings <= 10), 
        	CONSTRAINT uq_scheduling_profile_tenant_user UNIQUE (tenant_id, user_id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
        	id VARCHAR(50) NOT NULL, 
        	user_id VARCHAR(100) NOT NULL, 
        	session_token VARCHAR(200) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	session_data JSONB, 
        	user_preferences JSONB, 
        	last_activity TIMESTAMP WITH TIME ZONE, 
        	page_views INTEGER, 
        	actions_count INTEGER, 
        	is_active BOOLEAN, 
        	expires_at TIMESTAMP WITH TIME ZONE, 
        	client_ip VARCHAR(45), 
        	user_agent VARCHAR(500), 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	UNIQUE (session_token), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_endpoints (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	url TEXT NOT NULL, 
        	secret VARCHAR(255), 
        	events JSON NOT NULL, 
        	description VARCHAR(255), 
        	is_active BOOLEAN DEFAULT 'true' NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_experiences (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	workflow_type VARCHAR NOT NULL, 
        	input_data JSON NOT NULL, 
        	output_data JSON NOT NULL, 
        	feedback_score FLOAT, 
        	is_processed BOOLEAN, 
        	created_at TIMESTAMP WITH TIME ZONE, 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memory_profiles (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100) NOT NULL, 
        	agent_type VARCHAR(50), 
        	persona_name VARCHAR(200), 
        	persona_description TEXT, 
        	owner_user_id INTEGER, 
        	active_goals JSON NOT NULL, 
        	operating_rules JSON NOT NULL, 
        	domain_expertise JSON NOT NULL, 
        	profile_version INTEGER NOT NULL, 
        	is_active BOOLEAN NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(owner_user_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	entity_type VARCHAR(50) NOT NULL, 
        	entity_id INTEGER NOT NULL, 
        	parent_id INTEGER, 
        	body TEXT NOT NULL, 
        	is_deleted BOOLEAN DEFAULT 'false' NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(parent_id) REFERENCES comments (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dead_letter_entries (
        	id SERIAL NOT NULL, 
        	original_task_id VARCHAR(100) NOT NULL, 
        	execution_id VARCHAR(100) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	workflow_id VARCHAR(100), 
        	error_message TEXT NOT NULL, 
        	stack_trace TEXT, 
        	error_type VARCHAR(100), 
        	retry_count INTEGER, 
        	max_retries INTEGER, 
        	status VARCHAR(20) NOT NULL, 
        	failed_at TIMESTAMP WITH TIME ZONE, 
        	last_retry_at TIMESTAMP WITH TIME ZONE, 
        	resolved_at TIMESTAMP WITH TIME ZONE, 
        	resolved_by INTEGER, 
        	resolution_notes TEXT, 
        	task_metadata TEXT, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(resolved_by) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deletion_audit (
        	id SERIAL NOT NULL, 
        	entity_type VARCHAR(100) NOT NULL, 
        	entity_id VARCHAR(100) NOT NULL, 
        	deletion_reason VARCHAR(50) NOT NULL, 
        	legal_basis VARCHAR(255), 
        	deleted_by INTEGER, 
        	deleted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	tenant_id INTEGER DEFAULT '0' NOT NULL, 
        	entity_snapshot_hash VARCHAR(64), 
        	entity_metadata JSON, 
        	justification TEXT, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(deleted_by) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS email_campaigns (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	created_by INTEGER NOT NULL, 
        	name VARCHAR(255) NOT NULL, 
        	subject VARCHAR(255) NOT NULL, 
        	content TEXT NOT NULL, 
        	sender_email VARCHAR(255) NOT NULL, 
        	status campaignstatus DEFAULT 'draft' NOT NULL, 
        	segments JSON, 
        	recipient_count INTEGER DEFAULT '0' NOT NULL, 
        	scheduled_at TIMESTAMP WITH TIME ZONE, 
        	sent_at TIMESTAMP WITH TIME ZONE, 
        	is_deleted BOOLEAN DEFAULT 'false' NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(created_by) REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS entity_tags (
        	id SERIAL NOT NULL, 
        	tag_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	entity_type VARCHAR(50) NOT NULL, 
        	entity_id INTEGER NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	CONSTRAINT uq_entity_tags_unique UNIQUE (tag_id, entity_type, entity_id), 
        	FOREIGN KEY(tag_id) REFERENCES tags (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_results (
        	id SERIAL NOT NULL, 
        	run_id INTEGER, 
        	tenant_id INTEGER NOT NULL, 
        	query TEXT NOT NULL, 
        	response TEXT NOT NULL, 
        	contexts JSON NOT NULL, 
        	reference_answer TEXT, 
        	faithfulness FLOAT, 
        	relevance FLOAT, 
        	correctness FLOAT, 
        	precision FLOAT, 
        	recall FLOAT, 
        	context_precision FLOAT, 
        	context_recall FLOAT, 
        	latency_ms FLOAT, 
        	engine_version VARCHAR(50), 
        	model_name VARCHAR(100), 
        	metadata JSON, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(run_id) REFERENCES evaluation_runs (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS immune_antibodies (
        	id UUID NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	name VARCHAR NOT NULL, 
        	description VARCHAR, 
        	target_antigen VARCHAR NOT NULL, 
        	action_type VARCHAR NOT NULL, 
        	action_config JSONB, 
        	effectiveness FLOAT, 
        	trigger_count INTEGER, 
        	false_positive_count INTEGER, 
        	side_effects JSONB, 
        	created_from UUID, 
        	is_auto_generated BOOLEAN NOT NULL, 
        	is_active BOOLEAN NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE, 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(created_from) REFERENCES immune_memory_cells (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_items (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100), 
        	user_id INTEGER, 
        	workspace_id INTEGER, 
        	memory_type VARCHAR(20) NOT NULL, 
        	content TEXT NOT NULL, 
        	content_embedding VECTOR(1536), 
        	confidence FLOAT NOT NULL, 
        	importance FLOAT NOT NULL, 
        	source_type VARCHAR(50) NOT NULL, 
        	source_ref VARCHAR(200), 
        	privacy_scope VARCHAR(20) NOT NULL, 
        	status VARCHAR(20) NOT NULL, 
        	valid_from TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	valid_to TIMESTAMP WITH TIME ZONE, 
        	tags JSON NOT NULL, 
        	entities JSON NOT NULL, 
        	provenance JSON NOT NULL, 
        	dedup_hash VARCHAR(64), 
        	contradicts_item_id INTEGER, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	deleted_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL, 
        	FOREIGN KEY(contradicts_item_id) REFERENCES memory_items (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_retrieval_traces (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100), 
        	session_id INTEGER, 
        	user_id INTEGER, 
        	query_text TEXT NOT NULL, 
        	query_tokens INTEGER, 
        	result_item_ids JSON NOT NULL, 
        	result_count INTEGER NOT NULL, 
        	retrieval_method VARCHAR(20) NOT NULL, 
        	top_k_requested INTEGER, 
        	query_time_ms FLOAT, 
        	relevance_scores JSON, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	type VARCHAR(50) NOT NULL, 
        	title VARCHAR(255) NOT NULL, 
        	body TEXT, 
        	data JSON, 
        	channel VARCHAR(20) DEFAULT 'in_app' NOT NULL, 
        	is_read BOOLEAN DEFAULT 'false' NOT NULL, 
        	read_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP) NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS point_transactions (
        	id SERIAL NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	points INTEGER NOT NULL, 
        	action VARCHAR(50) NOT NULL, 
        	description TEXT, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS role_permissions (
        	id SERIAL NOT NULL, 
        	role_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	resource VARCHAR(100) NOT NULL, 
        	action VARCHAR(50) NOT NULL, 
        	conditions JSON, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_partner_feedback (
        	id VARCHAR(36) NOT NULL, 
        	partner_id VARCHAR(36) NOT NULL, 
        	reported_by VARCHAR(36), 
        	reporter_email VARCHAR(255), 
        	feedback_type VARCHAR(20) NOT NULL, 
        	severity VARCHAR(10) NOT NULL, 
        	category VARCHAR(20) NOT NULL, 
        	title VARCHAR(255) NOT NULL, 
        	description TEXT NOT NULL, 
        	reproduction_steps TEXT, 
        	expected_behavior TEXT, 
        	actual_behavior TEXT, 
        	environment JSON, 
        	attachments JSON, 
        	status VARCHAR(20) NOT NULL, 
        	priority INTEGER NOT NULL, 
        	assigned_to VARCHAR(36), 
        	resolution_notes TEXT, 
        	resolved_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(partner_id) REFERENCES scheduling_design_partners (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_sync_conflicts (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	integration_id VARCHAR(36) NOT NULL, 
        	local_event_id VARCHAR(36) NOT NULL, 
        	external_event_id VARCHAR(255) NOT NULL, 
        	conflict_type VARCHAR(30) NOT NULL, 
        	severity VARCHAR(10) NOT NULL, 
        	local_snapshot JSON NOT NULL, 
        	external_snapshot JSON NOT NULL, 
        	resolution_status VARCHAR(20) NOT NULL, 
        	resolution_strategy VARCHAR(30), 
        	resolved_by VARCHAR(36), 
        	resolved_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(integration_id) REFERENCES scheduling_calendar_integrations (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduling_webhook_registrations (
        	id VARCHAR(36) NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	integration_id VARCHAR(36) NOT NULL, 
        	provider VARCHAR(20) NOT NULL, 
        	channel_id VARCHAR(255), 
        	resource_id VARCHAR(255), 
        	subscription_id VARCHAR(255), 
        	client_state VARCHAR(255), 
        	expiration_date TIMESTAMP WITH TIME ZONE NOT NULL, 
        	is_active BOOLEAN NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(integration_id) REFERENCES scheduling_calendar_integrations (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS security_alerts (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	alert_id VARCHAR(64) NOT NULL, 
        	alert_type VARCHAR(50) NOT NULL, 
        	severity VARCHAR(20) NOT NULL, 
        	title VARCHAR(255) NOT NULL, 
        	description TEXT NOT NULL, 
        	details JSON, 
        	detection_rule VARCHAR(100), 
        	event_count INTEGER, 
        	first_event_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	last_event_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	source_ip VARCHAR(45), 
        	user_id INTEGER, 
        	affected_resources JSON, 
        	related_event_ids JSON, 
        	status VARCHAR(20) NOT NULL, 
        	acknowledged_by INTEGER, 
        	acknowledged_at TIMESTAMP WITH TIME ZONE, 
        	resolved_by INTEGER, 
        	resolved_at TIMESTAMP WITH TIME ZONE, 
        	resolution_notes TEXT, 
        	auto_response_taken BOOLEAN, 
        	auto_response_details JSON, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL, 
        	FOREIGN KEY(acknowledged_by) REFERENCES users (id) ON DELETE SET NULL, 
        	FOREIGN KEY(resolved_by) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS token_blacklist (
        	id SERIAL NOT NULL, 
        	jti VARCHAR(255) NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	token_hash VARCHAR(255) NOT NULL, 
        	revoked_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	revoked_by INTEGER, 
        	reason VARCHAR(255), 
        	PRIMARY KEY (id), 
        	UNIQUE (jti), 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(revoked_by) REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_records (
        	id SERIAL NOT NULL, 
        	user_id INTEGER, 
        	tenant_id INTEGER NOT NULL, 
        	metric_type VARCHAR(50) NOT NULL, 
        	value FLOAT NOT NULL, 
        	metadata_json JSON, 
        	timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_badges (
        	id SERIAL NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	badge_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	earned_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(badge_id) REFERENCES badges (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_email_preferences (
        	id SERIAL NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	newsletter_subscribed BOOLEAN DEFAULT 'true' NOT NULL, 
        	marketing_subscribed BOOLEAN DEFAULT 'true' NOT NULL, 
        	events_subscribed BOOLEAN DEFAULT 'true' NOT NULL, 
        	updates_subscribed BOOLEAN DEFAULT 'true' NOT NULL, 
        	unsubscribed_from JSON, 
        	unsubscribed_at TIMESTAMP WITH TIME ZONE, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_points (
        	id SERIAL NOT NULL, 
        	user_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	total_points INTEGER NOT NULL, 
        	level INTEGER NOT NULL, 
        	current_streak INTEGER NOT NULL, 
        	longest_streak INTEGER NOT NULL, 
        	last_activity_date TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_deliveries (
        	id SERIAL NOT NULL, 
        	webhook_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	event_type VARCHAR(100) NOT NULL, 
        	payload JSON NOT NULL, 
        	response_status INTEGER, 
        	response_body TEXT, 
        	attempt_count INTEGER DEFAULT '1' NOT NULL, 
        	next_retry_at TIMESTAMP WITH TIME ZONE, 
        	delivered_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(webhook_id) REFERENCES webhook_endpoints (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_templates (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	name VARCHAR(100) NOT NULL, 
        	description TEXT, 
        	status workflowstatus NOT NULL, 
        	version INTEGER NOT NULL, 
        	nodes JSON NOT NULL, 
        	edges JSON NOT NULL, 
        	metadata JSON, 
        	original_prompt TEXT, 
        	complexity VARCHAR(20), 
        	generation_model VARCHAR(50), 
        	created_by INTEGER, 
        	execution_count INTEGER, 
        	last_executed_at TIMESTAMP WITH TIME ZONE, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_versions (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	workflow_id VARCHAR NOT NULL, 
        	version_number INTEGER NOT NULL, 
        	created_by INTEGER NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
        	name VARCHAR NOT NULL, 
        	description VARCHAR, 
        	workflow_spec JSON NOT NULL, 
        	change_description TEXT, 
        	is_stable BOOLEAN, 
        	tags JSON, 
        	created_at_utc TIMESTAMP WITH TIME ZONE NOT NULL, 
        	updated_at_utc TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
        	FOREIGN KEY(created_by) REFERENCES users (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ab_tests (
        	id SERIAL NOT NULL, 
        	campaign_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	variant_a_subject VARCHAR(255) NOT NULL, 
        	variant_b_subject VARCHAR(255) NOT NULL, 
        	variant_a_content TEXT NOT NULL, 
        	variant_b_content TEXT NOT NULL, 
        	split_percentage INTEGER DEFAULT '50' NOT NULL, 
        	winner_variant VARCHAR(1), 
        	variant_a_open_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	variant_b_open_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	variant_a_click_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	variant_b_click_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(campaign_id) REFERENCES email_campaigns (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_profile_snapshots (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	profile_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100) NOT NULL, 
        	profile_version INTEGER NOT NULL, 
        	snapshot JSON NOT NULL, 
        	changed_by_user_id INTEGER, 
        	change_reason VARCHAR(200), 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(profile_id) REFERENCES agent_memory_profiles (id) ON DELETE CASCADE, 
        	FOREIGN KEY(changed_by_user_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_analytics (
        	id SERIAL NOT NULL, 
        	campaign_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	sent_count INTEGER DEFAULT '0' NOT NULL, 
        	delivered_count INTEGER DEFAULT '0' NOT NULL, 
        	open_count INTEGER DEFAULT '0' NOT NULL, 
        	click_count INTEGER DEFAULT '0' NOT NULL, 
        	bounce_count INTEGER DEFAULT '0' NOT NULL, 
        	unsubscribe_count INTEGER DEFAULT '0' NOT NULL, 
        	spam_count INTEGER DEFAULT '0' NOT NULL, 
        	open_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	click_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	bounce_rate FLOAT DEFAULT '0.0' NOT NULL, 
        	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(campaign_id) REFERENCES email_campaigns (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS campaign_segments (
        	id SERIAL NOT NULL, 
        	campaign_id INTEGER NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	filter_type VARCHAR(50) NOT NULL, 
        	filter_values JSON NOT NULL, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(campaign_id) REFERENCES email_campaigns (id) ON DELETE CASCADE, 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS session_memory_events (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	session_id INTEGER NOT NULL, 
        	agent_id VARCHAR(100) NOT NULL, 
        	user_id INTEGER, 
        	event_type VARCHAR(50) NOT NULL, 
        	event_data JSON NOT NULL, 
        	memory_candidate BOOLEAN NOT NULL, 
        	resolved_item_id INTEGER, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL, 
        	FOREIGN KEY(resolved_item_id) REFERENCES memory_items (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_change_logs (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	from_version_id INTEGER, 
        	to_version_id INTEGER NOT NULL, 
        	change_type VARCHAR NOT NULL, 
        	target_id VARCHAR, 
        	old_value JSON, 
        	new_value JSON, 
        	reason TEXT, 
        	created_at_utc TIMESTAMP WITH TIME ZONE NOT NULL, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id), 
        	FOREIGN KEY(from_version_id) REFERENCES workflow_versions (id), 
        	FOREIGN KEY(to_version_id) REFERENCES workflow_versions (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_instances (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	template_id INTEGER NOT NULL, 
        	template_version INTEGER NOT NULL, 
        	name VARCHAR(100), 
        	description TEXT, 
        	config JSON, 
        	input_data JSON, 
        	schedule_cron VARCHAR(100), 
        	is_scheduled BOOLEAN, 
        	next_run_at TIMESTAMP WITH TIME ZONE, 
        	is_active BOOLEAN, 
        	created_by INTEGER, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(template_id) REFERENCES workflow_templates (id) ON DELETE CASCADE, 
        	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_executions (
        	id SERIAL NOT NULL, 
        	tenant_id INTEGER NOT NULL, 
        	instance_id INTEGER NOT NULL, 
        	execution_id VARCHAR(64) NOT NULL, 
        	status executionstatus NOT NULL, 
        	trigger_type VARCHAR(50) NOT NULL, 
        	triggered_by INTEGER, 
        	input_data JSON, 
        	output_data JSON, 
        	node_states JSON, 
        	current_node VARCHAR(50), 
        	nodes_completed INTEGER, 
        	nodes_total INTEGER, 
        	progress_percent FLOAT, 
        	started_at TIMESTAMP WITH TIME ZONE, 
        	completed_at TIMESTAMP WITH TIME ZONE, 
        	duration_ms INTEGER, 
        	error_message TEXT, 
        	error_node_id VARCHAR(50), 
        	error_details JSON, 
        	retry_count INTEGER, 
        	max_retries INTEGER, 
        	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
        	updated_at TIMESTAMP WITH TIME ZONE, 
        	PRIMARY KEY (id), 
        	FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE CASCADE, 
        	FOREIGN KEY(instance_id) REFERENCES workflow_instances (id) ON DELETE CASCADE, 
        	FOREIGN KEY(triggered_by) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS tenant_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS session_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS user_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS event_subtype VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS severity VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS event_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS context JSON
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS event_timestamp TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS batch_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS tenant_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS metric_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS metric_name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS aggregation_level VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS time_bucket TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_sum FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_min FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_max FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_avg FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_p50 FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_p95 FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS value_p99 FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS dimensions JSON
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_metrics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS tenant_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS session_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS start_time TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS end_time TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS duration_seconds INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS page_view_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS event_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS error_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS actions JSON
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS device_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS browser VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS os VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS procedure_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS status VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS error_message VARCHAR(2000)
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS audit_trail JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_executions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS flow_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS domain_pack_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS category VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS description VARCHAR(2000)
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS intent_tags VARCHAR[]
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS prerequisites VARCHAR[]
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS estimated_duration_minutes INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS is_platform_template BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS procedure_metadata JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE procedure_metadata ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS agent_a VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS agent_b VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS connection_strength FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS last_communication TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS communication_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS successful_collaborations INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_synapses ADD COLUMN IF NOT EXISTS failed_collaborations INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS execution_id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS event_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS severity VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS details JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE aiqualityevents ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS day_of_week INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS hour_block INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS total_slots INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS busy_slots INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS free_slots INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS tentative_slots INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS availability_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS confidence FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS sample_weeks INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE availability_patterns ADD COLUMN IF NOT EXISTS last_updated TIMESTAMP WITHOUT TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS code VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS icon VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS color VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS points_required INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS is_secret BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE badges ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS amount_cents INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS currency VARCHAR(3)
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS external_ref VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS metadata JSON
        """
    )
    op.execute(
        """
        ALTER TABLE billing_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS tokens_used INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10, 4)
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS period_start TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS period_end TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS model_name VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS task_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE budget_usage ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS workflow_id VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS content BYTEA
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS size_bytes INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS created_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE c7_workflow_snapshots ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS id VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS session_id VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS user_message TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS cva_response TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS response_metadata JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS performance_data JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS conversation_turn INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS context_summary TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS user_feedback VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS feedback_details TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS attached_files JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS conversation_topic VARCHAR(200)
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS conversation_category VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS keywords JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE cva_conversations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS name VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS subject_template VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS content_template TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS category VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS is_public BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE email_templates ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS name VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS num_samples INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS status VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS avg_faithfulness FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS avg_precision FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS avg_recall FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS avg_context_precision FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS avg_answer_relevancy FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS avg_context_recall FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS error TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS metadata JSON
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS threat_signature VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS threat_type VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS threat_description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS antibodies_used JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS outcome JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS lessons_learned JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS reinforced_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS effectiveness_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE immune_memory_cells ADD COLUMN IF NOT EXISTS last_reinforced TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS content TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS entry_metadata JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS confidence_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE knowledge_entries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS event_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS event_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS agent_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS task_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS success BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS duration FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS context JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS metrics JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS session_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS confidence FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE learning_experiences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS sessions_processed INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS events_processed INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS items_created INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS items_archived INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS contradictions_found INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS error_message TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS run_metadata JSON
        """
    )
    op.execute(
        """
        ALTER TABLE memory_consolidation_runs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS agent_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS agent_type VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS department VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS registered_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS workload JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS emotional_state JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE organism_registry ADD COLUMN IF NOT EXISTS status VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS title VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS start_time TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS end_time TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS location VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS organizer_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS participants JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS status VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS priority INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS recurrence_rule VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS metadata_json JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_events ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS provider VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS provider_account_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS provider_calendar_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS access_token_encrypted TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS refresh_token_encrypted TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS token_expires_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS token_scope VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS sync_token VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_calendar_integrations ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS constraint_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS is_hard BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS parameters JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_constraints ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS name VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS industry VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS start_date TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS end_date TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS max_users INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS allowed_features JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS total_events_created INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS total_conflicts_detected INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS api_calls_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS error_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_design_partners ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS timezone_name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS working_hours_start TIME WITHOUT TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS working_hours_end TIME WITHOUT TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS preferred_duration_minutes INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS buffer_minutes INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS preferences_json JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_preferences ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS block_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS start_time TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS end_time TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS recurrence_rule VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS is_hard_block BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS label VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_time_blocks ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS signal_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS source_agent VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS target_agents JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS tier VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS payload_hash VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS payload_size_bytes INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS processed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS processing_latency_ms INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE signal_audit_log ADD COLUMN IF NOT EXISTS antibody_triggered VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE signal_cooldowns ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE signal_cooldowns ADD COLUMN IF NOT EXISTS signal_type VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE signal_cooldowns ADD COLUMN IF NOT EXISTS sender VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE signal_cooldowns ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS insight_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS title VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS confidence FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS impact_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS urgency_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS supporting_evidence JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS recommended_actions JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS risks JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS opportunities JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_insights ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS objective_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS title VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS priority INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS status VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS progress FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS success_criteria JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS key_results JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE strategic_objectives ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS strategy_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS strategy_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS status VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS analysis JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS recommendations JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS implementation_plan JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS success_metrics JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS confidence_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS context_data JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE strategies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE tags ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE tags ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE tags ADD COLUMN IF NOT EXISTS name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE tags ADD COLUMN IF NOT EXISTS color VARCHAR(7)
        """
    )
    op.execute(
        """
        ALTER TABLE tags ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS namespace VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS key VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS value JSON
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_custom_data ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS channel_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS bot_token VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS provider_config JSON
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_integrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS user_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS chronotype VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS preferred_morning_start TIME WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS preferred_morning_end TIME WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS preferred_afternoon_start TIME WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS preferred_afternoon_end TIME WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS focus_time_min_duration INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS protect_focus_time BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS default_prep_buffer INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS default_recovery_buffer INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS travel_buffer_minutes INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS max_meetings_per_day INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS max_consecutive_meetings INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS timezone VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS last_pattern_analysis TIMESTAMP WITHOUT TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS pattern_confidence FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITHOUT TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_scheduling_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITHOUT TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS id VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS user_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS session_token VARCHAR(200)
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS session_data JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS user_preferences JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS page_views INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS actions_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS client_ip VARCHAR(45)
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS user_agent VARCHAR(500)
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS url TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS secret VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS events JSON
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS description VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_endpoints ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS workflow_type VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS input_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS output_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS feedback_score FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS is_processed BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_experiences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS agent_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS persona_name VARCHAR(200)
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS persona_description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS owner_user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS active_goals JSON
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS operating_rules JSON
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS domain_expertise JSON
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS profile_version INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_memory_profiles ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS entity_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS parent_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS body TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE comments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS original_task_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS execution_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS workflow_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS error_message TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS stack_trace TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS error_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS retry_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS max_retries INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS failed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS last_retry_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS resolved_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS resolution_notes TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE dead_letter_entries ADD COLUMN IF NOT EXISTS task_metadata TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS entity_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS entity_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS deletion_reason VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS legal_basis VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS deleted_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS entity_snapshot_hash VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS entity_metadata JSON
        """
    )
    op.execute(
        """
        ALTER TABLE deletion_audit ADD COLUMN IF NOT EXISTS justification TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS created_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS name VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS subject VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS content TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS sender_email VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS status campaignstatus
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS segments JSON
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS recipient_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE email_campaigns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS tag_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS entity_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE entity_tags ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS run_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS query TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS response TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS contexts JSON
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS reference_answer TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS faithfulness FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS relevance FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS correctness FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS precision FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS recall FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS context_precision FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS context_recall FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS latency_ms FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS engine_version VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS model_name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS metadata JSON
        """
    )
    op.execute(
        """
        ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS id UUID
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS name VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS description VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS target_antigen VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS action_type VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS action_config JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS effectiveness FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS trigger_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS false_positive_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS side_effects JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS created_from UUID
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS is_auto_generated BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE immune_antibodies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS workspace_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS memory_type VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS content TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS content_embedding VECTOR(1536)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS confidence FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS importance FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS source_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS source_ref VARCHAR(200)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS privacy_scope VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS valid_from TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS valid_to TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS tags JSON
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS entities JSON
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS provenance JSON
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS dedup_hash VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS contradicts_item_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_items ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS session_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS query_text TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS query_tokens INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS result_item_ids JSON
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS result_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS retrieval_method VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS top_k_requested INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS query_time_ms FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS relevance_scores JSON
        """
    )
    op.execute(
        """
        ALTER TABLE memory_retrieval_traces ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS body TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS channel VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS read_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS points INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS action VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE point_transactions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS role_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS resource VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS action VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS conditions JSON
        """
    )
    op.execute(
        """
        ALTER TABLE role_permissions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS partner_id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS reported_by VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS reporter_email VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS feedback_type VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS severity VARCHAR(10)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS category VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS title VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS reproduction_steps TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS expected_behavior TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS actual_behavior TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS environment JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS attachments JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS priority INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS assigned_to VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS resolution_notes TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_partner_feedback ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS integration_id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS local_event_id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS external_event_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS conflict_type VARCHAR(30)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS severity VARCHAR(10)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS local_snapshot JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS external_snapshot JSON
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS resolution_status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS resolution_strategy VARCHAR(30)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS resolved_by VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_sync_conflicts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS integration_id VARCHAR(36)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS provider VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS channel_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS resource_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS subscription_id VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS client_state VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS expiration_date TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE scheduling_webhook_registrations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS alert_id VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS alert_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS severity VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS title VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS details JSON
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS detection_rule VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS event_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS first_event_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS source_ip VARCHAR(45)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS affected_resources JSON
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS related_event_ids JSON
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS status VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS acknowledged_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS resolved_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS resolution_notes TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS auto_response_taken BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS auto_response_details JSON
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE security_alerts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS jti VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS token_hash VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS revoked_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE token_blacklist ADD COLUMN IF NOT EXISTS reason VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS metric_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS value FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS metadata_json JSON
        """
    )
    op.execute(
        """
        ALTER TABLE usage_records ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_badges ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_badges ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_badges ADD COLUMN IF NOT EXISTS badge_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_badges ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_badges ADD COLUMN IF NOT EXISTS earned_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS newsletter_subscribed BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS marketing_subscribed BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS events_subscribed BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS updates_subscribed BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS unsubscribed_from JSON
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS unsubscribed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_email_preferences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS total_points INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS level INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS current_streak INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS longest_streak INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS last_activity_date TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE user_points ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS webhook_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS event_type VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS payload JSON
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS response_status INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS response_body TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS attempt_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS status workflowstatus
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS version INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS nodes JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS edges JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS metadata JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS original_prompt TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS complexity VARCHAR(20)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS generation_model VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS created_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS execution_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS last_executed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_templates ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS workflow_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS version_number INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS created_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS name VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS description VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS workflow_spec JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS change_description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS is_stable BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS tags JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS created_at_utc TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_versions ADD COLUMN IF NOT EXISTS updated_at_utc TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS campaign_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_a_subject VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_b_subject VARCHAR(255)
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_a_content TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_b_content TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS split_percentage INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS winner_variant VARCHAR(1)
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_a_open_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_b_open_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_a_click_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS variant_b_click_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE ab_tests ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS profile_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS profile_version INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS snapshot JSON
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS changed_by_user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS change_reason VARCHAR(200)
        """
    )
    op.execute(
        """
        ALTER TABLE agent_profile_snapshots ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS campaign_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS sent_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS delivered_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS open_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS click_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS bounce_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS unsubscribe_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS spam_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS open_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS click_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS bounce_rate FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_analytics ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_segments ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_segments ADD COLUMN IF NOT EXISTS campaign_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_segments ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_segments ADD COLUMN IF NOT EXISTS filter_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_segments ADD COLUMN IF NOT EXISTS filter_values JSON
        """
    )
    op.execute(
        """
        ALTER TABLE campaign_segments ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS session_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS agent_id VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS user_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS event_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS event_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS memory_candidate BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS resolved_item_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE session_memory_events ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS from_version_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS to_version_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS change_type VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS target_id VARCHAR
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS old_value JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS new_value JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS reason TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_change_logs ADD COLUMN IF NOT EXISTS created_at_utc TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS template_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS template_version INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS name VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS description TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS config JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS input_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS schedule_cron VARCHAR(100)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS is_scheduled BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS next_run_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS is_active BOOLEAN
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS created_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS tenant_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS instance_id INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS execution_id VARCHAR(64)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS status executionstatus
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS triggered_by INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS input_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS output_data JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS node_states JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS current_node VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS nodes_completed INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS nodes_total INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS progress_percent FLOAT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS started_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS duration_ms INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS error_message TEXT
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS error_node_id VARCHAR(50)
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS error_details JSON
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS retry_count INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS max_retries INTEGER
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        ALTER TABLE workflow_executions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_batch ON analytics_events (batch_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_batch_id ON analytics_events (batch_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_created_at ON analytics_events (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_event_subtype ON analytics_events (event_subtype)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_event_timestamp ON analytics_events (event_timestamp)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_event_type ON analytics_events (event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_id ON analytics_events (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_is_deleted ON analytics_events (is_deleted)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_session_id ON analytics_events (session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_session_type ON analytics_events (session_id, event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_severity ON analytics_events (severity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_tenant_id ON analytics_events (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_tenant_timestamp ON analytics_events (tenant_id, event_timestamp)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_user_id ON analytics_events (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_events_user_timestamp ON analytics_events (user_id, event_timestamp)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_metrics_aggregation_level ON analytics_metrics (aggregation_level)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_metrics_id ON analytics_metrics (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_metrics_metric_type ON analytics_metrics (metric_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_metrics_tenant_id ON analytics_metrics (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_metrics_time_bucket ON analytics_metrics (time_bucket)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_metrics_tenant_bucket ON analytics_metrics (tenant_id, time_bucket)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_metrics_tenant_type_bucket ON analytics_metrics (tenant_id, metric_type, time_bucket)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_sessions_id ON analytics_sessions (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_sessions_is_active ON analytics_sessions (is_active)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_analytics_sessions_session_id ON analytics_sessions (session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_sessions_tenant_id ON analytics_sessions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_analytics_sessions_user_id ON analytics_sessions (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_sessions_tenant_start ON analytics_sessions (tenant_id, start_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_sessions_tenant_user ON analytics_sessions (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_executions_created_at ON procedure_executions (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_executions_procedure ON procedure_executions (procedure_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_executions_status ON procedure_executions (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_executions_tenant ON procedure_executions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_executions_procedure_id ON procedure_executions (procedure_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_executions_status ON procedure_executions (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_executions_tenant_id ON procedure_executions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_metadata_domain_pack ON procedure_metadata (domain_pack_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_metadata_flow ON procedure_metadata (flow_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_metadata_intent_tags ON procedure_metadata USING gin (intent_tags)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_procedure_metadata_tenant ON procedure_metadata (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_metadata_domain_pack_id ON procedure_metadata (domain_pack_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_metadata_flow_id ON procedure_metadata (flow_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_metadata_intent_tags ON procedure_metadata (intent_tags)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_procedure_metadata_tenant_id ON procedure_metadata (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_synapses_strength ON agent_synapses (tenant_id, connection_strength)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_quality_events_created_at ON aiqualityevents (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_quality_events_execution ON aiqualityevents (execution_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_quality_events_severity ON aiqualityevents (severity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_quality_events_tenant_id ON aiqualityevents (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ai_quality_events_type ON aiqualityevents (event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_aiqualityevents_execution_id ON aiqualityevents (execution_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_aiqualityevents_tenant_id ON aiqualityevents (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_availability_patterns_tenant_id ON availability_patterns (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_availability_patterns_user_id ON availability_patterns (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_badges_id ON badges (id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_badges_tenant_code ON badges (tenant_id, code)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_billing_events_created_at ON billing_events (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_billing_events_event_type ON billing_events (event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_billing_events_tenant_id ON billing_events (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_usage_agent ON budget_usage (tenant_id, agent_id, period_start)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_usage_tenant_period ON budget_usage (tenant_id, period_start)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_budget_usage_agent_id ON budget_usage (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_budget_usage_period_start ON budget_usage (period_start)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_budget_usage_tenant_id ON budget_usage (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_c7_snapshot_workflow_time ON c7_workflow_snapshots (workflow_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_c7_workflow_snapshots_tenant_id ON c7_workflow_snapshots (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_c7_workflow_snapshots_workflow_id ON c7_workflow_snapshots (workflow_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_conversations_tenant_id ON cva_conversations (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_created_at ON cva_conversations (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_session_id ON cva_conversations (session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_tenant_id ON cva_conversations (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_topic ON cva_conversations (conversation_topic)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_turn ON cva_conversations (conversation_turn)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_cva_user_id ON cva_conversations (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_templates_tenant_id ON email_templates (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_run_created ON evaluation_runs (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_run_tenant_status ON evaluation_runs (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_evaluation_runs_id ON evaluation_runs (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_evaluation_runs_tenant_id ON evaluation_runs (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_effectiveness ON immune_memory_cells (effectiveness_score)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_tenant_signature ON immune_memory_cells (tenant_id, threat_signature)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_type ON immune_memory_cells (threat_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_immune_memory_cells_tenant_id ON immune_memory_cells (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_confidence_created ON knowledge_entries (confidence_score, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_created_type ON knowledge_entries (created_at, type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_search ON knowledge_entries (type, created_at, confidence_score)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_tenant_type ON knowledge_entries (tenant_id, type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_knowledge_type_confidence ON knowledge_entries (type, confidence_score)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_entries_created_at ON knowledge_entries (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_entries_id ON knowledge_entries (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_entries_tenant_id ON knowledge_entries (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_knowledge_entries_type ON knowledge_entries (type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_agent_task ON learning_experiences (agent_id, task_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_event_time ON learning_experiences (event_type, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_performance ON learning_experiences (agent_id, task_type, success, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_recent ON learning_experiences (created_at, agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_success_time ON learning_experiences (success, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_learning_tenant_agent ON learning_experiences (tenant_id, agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_agent_id ON learning_experiences (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_created_at ON learning_experiences (created_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_learning_experiences_event_id ON learning_experiences (event_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_event_type ON learning_experiences (event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_id ON learning_experiences (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_session_id ON learning_experiences (session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_success ON learning_experiences (success)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_task_type ON learning_experiences (task_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_tenant_id ON learning_experiences (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_learning_experiences_user_id ON learning_experiences (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mcr_tenant_started ON memory_consolidation_runs (tenant_id, started_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mcr_tenant_status ON memory_consolidation_runs (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_consolidation_runs_agent_id ON memory_consolidation_runs (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_consolidation_runs_status ON memory_consolidation_runs (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_consolidation_runs_tenant_id ON memory_consolidation_runs (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_organism_heartbeat ON organism_registry (last_heartbeat)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_organism_status ON organism_registry (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_organism_tenant_agent ON organism_registry (tenant_id, agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_organism_registry_tenant_id ON organism_registry (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cal_event_tenant_organizer ON scheduling_calendar_events (tenant_id, organizer_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cal_event_tenant_time ON scheduling_calendar_events (tenant_id, start_time, end_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cal_event_tenant_user ON scheduling_calendar_events (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_events_deleted_at ON scheduling_calendar_events (deleted_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_events_end_time ON scheduling_calendar_events (end_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_events_organizer_id ON scheduling_calendar_events (organizer_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_events_start_time ON scheduling_calendar_events (start_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_events_tenant_id ON scheduling_calendar_events (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_events_user_id ON scheduling_calendar_events (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cal_integ_provider ON scheduling_calendar_integrations (tenant_id, provider)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cal_integ_tenant_user ON scheduling_calendar_integrations (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_integrations_deleted_at ON scheduling_calendar_integrations (deleted_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_integrations_tenant_id ON scheduling_calendar_integrations (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_calendar_integrations_user_id ON scheduling_calendar_integrations (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_constraint_tenant_user ON scheduling_constraints (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_constraints_deleted_at ON scheduling_constraints (deleted_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_constraints_tenant_id ON scheduling_constraints (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_constraints_user_id ON scheduling_constraints (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_design_partners_tenant_id ON scheduling_design_partners (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pref_tenant_user ON scheduling_preferences (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_preferences_deleted_at ON scheduling_preferences (deleted_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_preferences_tenant_id ON scheduling_preferences (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_preferences_user_id ON scheduling_preferences (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_time_block_tenant_time ON scheduling_time_blocks (tenant_id, start_time, end_time)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_time_block_tenant_user ON scheduling_time_blocks (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_time_blocks_deleted_at ON scheduling_time_blocks (deleted_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_time_blocks_tenant_id ON scheduling_time_blocks (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_time_blocks_user_id ON scheduling_time_blocks (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_audit_agent ON signal_audit_log (source_agent)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_audit_tenant_time ON signal_audit_log (tenant_id, processed_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_audit_tier ON signal_audit_log (tier)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_signal_audit_log_signal_id ON signal_audit_log (signal_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_cooldown_expires ON signal_cooldowns (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_signal_cooldowns_expires_at ON signal_cooldowns (expires_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_strategic_insights_insight_id ON strategic_insights (insight_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategic_insights_tenant ON strategic_insights (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategic_insights_type ON strategic_insights (strategy_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategic_obj_status ON strategic_objectives (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategic_obj_tenant ON strategic_objectives (tenant_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_strategic_objectives_objective_id ON strategic_objectives (objective_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_strategies_strategy_id ON strategies (strategy_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategies_tenant ON strategies (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_strategies_type ON strategies (tenant_id, strategy_type, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_tags_tenant_id ON tags (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_tenant_custom_data_tenant_ns ON tenant_custom_data (tenant_id, namespace)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_integration_tenant_channel ON tenant_integrations (tenant_id, channel_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_tenant_integrations_id ON tenant_integrations (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_scheduling_profiles_tenant_id ON user_scheduling_profiles (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_scheduling_profiles_user_id ON user_scheduling_profiles (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_activity ON user_sessions (last_activity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_expires ON user_sessions (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_tenant_id ON user_sessions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_token ON user_sessions (session_token)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_user ON user_sessions (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_sessions_tenant_id ON user_sessions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_endpoints_is_active ON webhook_endpoints (is_active)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_endpoints_tenant_id ON webhook_endpoints (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_exp_processed ON workflow_experiences (is_processed, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_exp_tenant ON workflow_experiences (tenant_id, workflow_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_experiences_tenant_id ON workflow_experiences (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_amp_owner ON agent_memory_profiles (tenant_id, owner_user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_amp_tenant_agent ON agent_memory_profiles (tenant_id, agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_amp_tenant_agent_active ON agent_memory_profiles (tenant_id, agent_id, is_active)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_memory_profiles_agent_id ON agent_memory_profiles (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_memory_profiles_owner_user_id ON agent_memory_profiles (owner_user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_memory_profiles_tenant_id ON agent_memory_profiles (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_comments_entity ON comments (entity_type, entity_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_comments_parent_id ON comments (parent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_comments_tenant_id ON comments (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dlq_execution ON dead_letter_entries (execution_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dlq_failed_at ON dead_letter_entries (failed_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dlq_tenant_status ON dead_letter_entries (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dead_letter_entries_execution_id ON dead_letter_entries (execution_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dead_letter_entries_original_task_id ON dead_letter_entries (original_task_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_dead_letter_entries_tenant_id ON dead_letter_entries (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_deletion_audit_entity_id ON deletion_audit (entity_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_deletion_audit_entity_type ON deletion_audit (entity_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_campaigns_scheduled_at ON email_campaigns (scheduled_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_campaigns_status ON email_campaigns (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_email_campaigns_tenant_id ON email_campaigns (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_entity_tags_entity ON entity_tags (entity_type, entity_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_entity_tags_tenant_id ON entity_tags (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_faithfulness ON evaluation_results (faithfulness)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_run_id ON evaluation_results (run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_eval_tenant_created ON evaluation_results (tenant_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_evaluation_results_id ON evaluation_results (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_evaluation_results_run_id ON evaluation_results (run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_evaluation_results_tenant_id ON evaluation_results (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_antibodies_action ON immune_antibodies (action_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_antibodies_active ON immune_antibodies (is_active)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_antibodies_target ON immune_antibodies (target_antigen)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_antibodies_tenant_name ON immune_antibodies (tenant_id, name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_immune_antibodies_tenant_id ON immune_antibodies (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mi_dedup_hash ON memory_items (tenant_id, dedup_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mi_source ON memory_items (tenant_id, source_type, source_ref)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mi_tenant_agent_created ON memory_items (tenant_id, agent_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mi_tenant_agent_type_status ON memory_items (tenant_id, agent_id, memory_type, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mi_tenant_status_scope ON memory_items (tenant_id, status, privacy_scope)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_agent_id ON memory_items (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_dedup_hash ON memory_items (dedup_hash)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_memory_type ON memory_items (memory_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_privacy_scope ON memory_items (privacy_scope)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_status ON memory_items (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_tenant_id ON memory_items (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_user_id ON memory_items (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_items_workspace_id ON memory_items (workspace_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mrt_tenant_agent ON memory_retrieval_traces (tenant_id, agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mrt_tenant_created ON memory_retrieval_traces (tenant_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mrt_tenant_session ON memory_retrieval_traces (tenant_id, session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_retrieval_traces_agent_id ON memory_retrieval_traces (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_retrieval_traces_created_at ON memory_retrieval_traces (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_retrieval_traces_session_id ON memory_retrieval_traces (session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_memory_retrieval_traces_tenant_id ON memory_retrieval_traces (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_notifications_created_at ON notifications (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_notifications_is_read ON notifications (is_read)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_notifications_tenant_user ON notifications (tenant_id, user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_point_transactions_id ON point_transactions (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_point_transactions_tenant ON point_transactions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_point_transactions_user ON point_transactions (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_role_permissions_id ON role_permissions (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_role_permissions_resource ON role_permissions (resource)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_role_permissions_role_id ON role_permissions (role_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_role_permissions_tenant_id ON role_permissions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_feedback_created ON scheduling_partner_feedback (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_feedback_severity ON scheduling_partner_feedback (severity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_feedback_status ON scheduling_partner_feedback (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_partner_feedback_partner_id ON scheduling_partner_feedback (partner_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_conflicts_integration ON scheduling_sync_conflicts (integration_id, resolution_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_conflicts_status ON scheduling_sync_conflicts (resolution_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_sync_conflicts_integration_id ON scheduling_sync_conflicts (integration_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_sync_conflicts_tenant_id ON scheduling_sync_conflicts (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_webhook_registrations_integration_id ON scheduling_webhook_registrations (integration_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_scheduling_webhook_registrations_tenant_id ON scheduling_webhook_registrations (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_channel_id ON scheduling_webhook_registrations (channel_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_expiration ON scheduling_webhook_registrations (expiration_date)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_subscription_id ON scheduling_webhook_registrations (subscription_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alert_status_severity ON security_alerts (status, severity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alert_tenant_created ON security_alerts (tenant_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alert_tenant_severity ON security_alerts (tenant_id, severity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_alert_tenant_status ON security_alerts (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_security_alerts_alert_id ON security_alerts (alert_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_security_alerts_alert_type ON security_alerts (alert_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_security_alerts_created_at ON security_alerts (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_security_alerts_id ON security_alerts (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_security_alerts_severity ON security_alerts (severity)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_security_alerts_status ON security_alerts (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_security_alerts_tenant_id ON security_alerts (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires ON token_blacklist (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_token_blacklist_user ON token_blacklist (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_token_blacklist_expires_at ON token_blacklist (expires_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_token_blacklist_id ON token_blacklist (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_token_blacklist_user_id ON token_blacklist (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_usage_records_id ON usage_records (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_usage_records_metric_type ON usage_records (metric_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_usage_records_tenant_id ON usage_records (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_usage_records_timestamp ON usage_records (timestamp)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_usage_records_user_id ON usage_records (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_badges_id ON user_badges (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_badges_tenant ON user_badges (tenant_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_user_badges_user_badge ON user_badges (user_id, badge_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_email_preferences_tenant_id ON user_email_preferences (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_email_preferences_user_id ON user_email_preferences (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_points_id ON user_points (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_user_points_tenant_level ON user_points (tenant_id, level)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_user_points_user_tenant ON user_points (user_id, tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_event_type ON webhook_deliveries (event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_tenant_id ON webhook_deliveries (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_webhook_id ON webhook_deliveries (webhook_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_template_created_by ON workflow_templates (created_by)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_template_tenant_name ON workflow_templates (tenant_id, name)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_template_tenant_status ON workflow_templates (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_templates_created_by ON workflow_templates (created_by)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_templates_id ON workflow_templates (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_templates_status ON workflow_templates (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_templates_tenant_id ON workflow_templates (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_created_at ON workflow_versions (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_tenant_created ON workflow_versions (tenant_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_tenant_id ON workflow_versions (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_tenant_workflow ON workflow_versions (tenant_id, workflow_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_version_number ON workflow_versions (version_number)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_versions_workflow_id ON workflow_versions (workflow_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ab_tests_campaign_id ON ab_tests (campaign_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_aps_profile_version ON agent_profile_snapshots (profile_id, profile_version)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_aps_tenant_agent ON agent_profile_snapshots (tenant_id, agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_profile_snapshots_agent_id ON agent_profile_snapshots (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_profile_snapshots_created_at ON agent_profile_snapshots (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_profile_snapshots_profile_id ON agent_profile_snapshots (profile_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_agent_profile_snapshots_tenant_id ON agent_profile_snapshots (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_campaign_analytics_campaign_id ON campaign_analytics (campaign_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_campaign_segments_campaign_id ON campaign_segments (campaign_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sme_tenant_agent_created ON session_memory_events (tenant_id, agent_id, created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sme_tenant_candidates ON session_memory_events (tenant_id, memory_candidate, resolved_item_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sme_tenant_session ON session_memory_events (tenant_id, session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_agent_id ON session_memory_events (agent_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_created_at ON session_memory_events (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_event_type ON session_memory_events (event_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_memory_candidate ON session_memory_events (memory_candidate)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_session_id ON session_memory_events (session_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_tenant_id ON session_memory_events (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_session_memory_events_user_id ON session_memory_events (user_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_change_logs_tenant ON workflow_change_logs (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_change_logs_tenant_id ON workflow_change_logs (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_change_logs_versions ON workflow_change_logs (from_version_id, to_version_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_instance_scheduled ON workflow_instances (is_scheduled, next_run_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_instance_template ON workflow_instances (template_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_instance_tenant ON workflow_instances (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_instances_id ON workflow_instances (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_instances_template_id ON workflow_instances (template_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_instances_tenant_id ON workflow_instances (tenant_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_execution_created ON workflow_executions (created_at)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_execution_instance ON workflow_executions (instance_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workflow_execution_tenant_status ON workflow_executions (tenant_id, status)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_executions_execution_id ON workflow_executions (execution_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_executions_id ON workflow_executions (id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_executions_instance_id ON workflow_executions (instance_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_executions_status ON workflow_executions (status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_workflow_executions_tenant_id ON workflow_executions (tenant_id)
        """
    )


def downgrade() -> None:
    """Ruimt UITSLUITEND op wat deze upgrade daadwerkelijk heeft aangemaakt.

    Een onvoorwaardelijke downgrade zou op een bestaande database 71 tabellen MET
    data droppen, waaronder AVG-bewijs en facturatie (Gate 2-review, HIGH-1).
    """
    op.execute(
        """
        DO $$
        DECLARE r RECORD;
        BEGIN
            IF to_regclass('public._baseline_20260817_created') IS NULL THEN
                RETURN;
            END IF;
            FOR r IN SELECT tabel FROM _baseline_20260817_created LOOP
                EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', r.tabel);
            END LOOP;
            EXECUTE 'DROP TABLE IF EXISTS _baseline_20260817_created';
        END $$;
        """
    )
    # ZONDER CASCADE, en dat is het hele punt (Gate 2-review ronde 2, bevinding A).
    # `DROP TYPE ... CASCADE` stond hier onvoorwaardelijk en verwijderde daarmee ook de
    # KOLOM uit tabellen die deze migratie nooit heeft aangemaakt -- gereproduceerd: de
    # kolom `status` verdween uit een bestaande tabel, met alleen een NOTICE. Dat is exact
    # de fout die een paar regels hierboven juist wordt gerepareerd.
    #
    # Nu blijft een type dat nog ergens in gebruik is gewoon staan: PostgreSQL weigert de
    # DROP met `dependent_objects_still_exist`, en die vangen we op. Een type dat alleen
    # door de zojuist verwijderde tabellen werd gebruikt, verdwijnt wel.
    for enaam in _ENUMS:
        op.execute(
            f"""
            DO $$ BEGIN
                DROP TYPE IF EXISTS {enaam};
            EXCEPTION WHEN dependent_objects_still_exist THEN NULL;
            END $$;
            """
        )
