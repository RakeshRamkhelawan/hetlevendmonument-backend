"""
Central model import registry.

Importing this module ensures ALL SQLAlchemy model classes are registered
with their respective Base metadata. Used by:
- Alembic env.py for autogenerate
- Test schema setup
- Database initialization scripts

This prevents "relation X does not exist" errors caused by models
that were never imported and therefore never registered.
"""

# ---------------------------------------------------------------------------
# core (misc)
# ---------------------------------------------------------------------------
import src.core.activepieces.models
import src.core.middleware.audit_middleware

# ---------------------------------------------------------------------------
# core.agents
# ---------------------------------------------------------------------------
import src.core.agents.budget_manager

# ---------------------------------------------------------------------------
# core.als (Adaptive Learning System models)
# ---------------------------------------------------------------------------
import src.core.als.models.agent_synapse
import src.core.als.models.collective_knowledge
import src.core.als.models.immune_antibody
import src.core.als.models.immune_memory_cell
import src.core.als.models.organism_registry
import src.core.als.models.signal_audit_log
import src.core.als.models.signal_cooldown

# ---------------------------------------------------------------------------
# core.agents
# ---------------------------------------------------------------------------
import src.core.agents.models
import src.core.agents.strategy_models
import src.core.analytics.models
import src.core.auth.models.account_lockout
import src.core.auth.oauth2_service
import src.core.auth.two_factor_auth
import src.core.autonomous_workflow.models
import src.core.company.models
import src.core.conversations.models

# ---------------------------------------------------------------------------
# copilot / council (decision_contests for GDPR art. 22)
# ---------------------------------------------------------------------------
import src.core.copilot.audit.models
import src.core.copilot.council.contest_models
import src.core.copilot.notification.preferences_repo
import src.core.database.gdpr_deletion
import src.core.database.models.analytics
import src.core.database.models.experiment
import src.core.feature_flags.models
import src.core.focus_builder.models
import src.core.governance.accuracy_monitor
import src.core.governance.alert_manager
import src.core.governance.authority_reporting
import src.core.governance.models
import src.core.governance.quality_management
import src.core.governance.risk_register
import src.core.knowledge.models

# ---------------------------------------------------------------------------
# core.learning
# ---------------------------------------------------------------------------
import src.core.learning.models
import src.core.learning.persistence_models
import src.core.learning.twin_models

# ---------------------------------------------------------------------------
# core.models
# ---------------------------------------------------------------------------
import src.core.models.agent_config
import src.core.models.campaign_models
import src.core.models.critique_models
# Toegevoegd 2026-08-17 (ADR-036 OP-147): het consent-model van de Digital Twin stond
# niet in de registratie. Verplaatst 2026-09-02 uit `src.core.api.v1.digital_twin.models`
# naar hier -- die locatie schond het "Infrastructuurlaag mag niet API-laag importeren"-
# contract in `.importlinter` (dit bestand importeerde de API-laag).
import src.core.models.digital_twin_models
import src.core.models.evaluation_models
import src.core.models.foundation_content
import src.core.models.gamification_models
# Toegevoegd 2026-08-17 (ADR-036 OP-140/OP-147): stond hier niet, waardoor de drie
# HR-vaardighedentabellen niet in `Base.metadata` kwamen. Gevolg: `create_all` maakte ze
# alleen aan als een test het model toevallig zelf importeerde, en `alembic autogenerate`
# zou ze als OVERBODIG zien en een DROP emitteren.
import src.core.models.hr_skills_models

# Toegevoegd 2026-08-22 (BE-AGT-058, Fase 3): zelfde OP-140/OP-147-valkuil als hr_skills_models
# hierboven -- een model dat hier niet geregistreerd wordt is onzichtbaar voor
# `alembic autogenerate` en voor `create_all` in tests.
import src.core.models.hr_training_models
# Toegevoegd 2026-10-11 (HR-pilot dag 3): zelfde OP-140/OP-147-valkuil als hierboven.
import src.core.models.hr_deadline_models
# Toegevoegd 2026-10-14 (pakket aanzetten dag 1): zelfde OP-140/OP-147-valkuil als hierboven.
import src.core.models.tenant_pack_activation_models
# Toegevoegd 2026-10-20 (noodstop per klant): zelfde OP-140/OP-147-valkuil als hierboven.
import src.core.models.tenant_noodstop_models

# Toegevoegd 2026-10-20 (ActivePieces-verbinding per klant): zelfde OP-140/OP-147-valkuil.
import src.core.models.tenant_ap_verbinding_models
import src.core.models.integration_models
import src.core.models.mission_models

# Toegevoegd 2026-10-05 (debiteurenagent dag 2): zelfde OP-140/OP-147-valkuil als
# receivable_models hieronder.
import src.core.models.outgoing_message_models
import src.core.models.persona_models
import src.core.models.rbac_models

# Toegevoegd 2026-10-04 (debiteurenagent dag 1): zelfde OP-140/OP-147-valkuil als
# hr_skills_models hierboven.
import src.core.models.receivable_models

# Toegevoegd 2026-10-24 (crediteuren dag 1): zelfde OP-140/OP-147-valkuil als receivable_models hierboven.
import src.core.models.payable_models

# Toegevoegd 2026-10-10 (ROI eerlijk gemeten): zelfde OP-140/OP-147-valkuil als hierboven.
import src.core.models.roi_models
import src.core.models.tenant_custom_data

# Toegevoegd 2026-09-20 (fase 2 lokaal-eerst LLM): dezelfde OP-140/OP-147-valkuil als
# hr_skills_models hierboven -- zonder registratie is de tabel onzichtbaar voor
# `alembic autogenerate` en voor `create_all` in tests.
import src.core.models.tenant_llm_provider_models
import src.core.models.usage_models
import src.core.models.workflow_models
import src.core.models.workflow_version_models
import src.core.notifications.inbound.models
import src.core.procedures.models

# ---------------------------------------------------------------------------
# core.scheduling
# ---------------------------------------------------------------------------
import src.core.scheduling.integrations.models
import src.core.scheduling.models
import src.core.scheduling.partners.models
import src.core.scheduling.smart.models
import src.core.scheduling.webhooks.models
import src.core.tool_broker.models
import src.core.workflow.dead_letter_queue
import src.core.workflow.models

# ---------------------------------------------------------------------------
# domains
# ---------------------------------------------------------------------------
import src.domains.agentic.models
import src.domains.billing.models
import src.domains.canvas.models
import src.domains.comments.models
import src.domains.documents.models
import src.domains.flows.models
import src.domains.memory.models
import src.domains.notifications.models
import src.domains.tagging.models
import src.domains.tasks.models
import src.domains.webhooks.models
