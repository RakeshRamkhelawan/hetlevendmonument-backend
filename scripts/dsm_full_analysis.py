"""Full weighted DSM analysis -- alle modules, test-bestanden uitgesloten."""

import ast
import collections
from pathlib import Path

MODULE_MAP = {
    "src.core.middleware": "tenancy",
    "src.core.middleware.tenant_context": "shared",  # ContextVar + FastAPI dep functions -- cross-cutting foundation, zero src.* imports
    "src.core.ratelimit": "tenancy",
    "src.core.auth": "auth",
    "src.core.auth.models": "shared",  # ORM model definitions (AccountLockout etc.) -- foundational data, not auth logic
    "src.core.security": "auth",
    "src.core.security.rate_limiter": "shared",  # SP-DSM-016 dag 4: Redis rate-limit utility -- infra primitive, zero src.* imports; asymmetrisch patroon SOURCE_DIRS["auth"] ongewijzigd
    "src.core.hardening": "auth",
    "src.core.governance": "governance",
    "src.core.governance.event_handlers": "integrations",  # SP-DSM-012: event-bus adapter, niet worker
    "src.core.governance.dsar_notifications": "integrations",  # SP-DSM-011: governance_worker pattern
    "src.core.governance_v2": "governance",
    "src.core.copilot": "agent_runtime",
    "src.core.ethics": "governance",
    "src.core.ai_quality": "domain_pack",
    "src.core.audit": "governance",
    "src.core.traceability": "governance",
    "src.core.ai": "agent_runtime",
    "src.core.autonomy": "agent_runtime",
    "src.core.services.audit_service": "governance",
    "src.core.services.usage_service": "infra",
    "src.core.services.subscription_cache": "infra",
    "src.core.scheduling.api": "core_api",  # route-handlers horen bij core_api, niet infra
    "src.core.agents": "agent_runtime",
    "src.core.agents.models": "shared",  # SP-DSM-017 dag 1: Agent ORM model definitions -- foundational data (cf. auth.models, workflow.models); sluit tenancy->agent_runtime backward dep
    "src.core.types": "shared",
    "src.core.als": "agent_runtime",
    "src.core.services": "agent_runtime",
    "src.core.services.email": "integrations",  # External email communication -- belongs with integrations, not agent_runtime
    "src.core.services.rbac_service": "auth",  # RBAC = auth concern; auth code imports this, not agent_runtime logic
    "src.core.workflow": "agent_runtime",
    "src.core.workflow.models": "shared",  # SQLAlchemy ORM model definitions (C7Workflow etc.) -- foundational data, not workflow logic
    "src.core.learning": "agent_runtime",
    "src.core.learning.loop": "shared",  # Pydantic data models (LearningInsight/AdaptationRule) used by governance; LearningLoop DB access is a pre-existing layering gap addressed separately
    "src.core.orchestrator": "agent_runtime",
    "src.core.runtime": "agent_runtime",
    "src.core.strategy": "agent_runtime",
    "src.core.routing": "agent_runtime",
    "src.core.semantic_router": "agent_runtime",
    "src.core.awareness": "agent_runtime",
    "src.core.intelligence": "agent_runtime",
    "src.core.emergence": "agent_runtime",
    "src.core.optimization": "agent_runtime",
    "src.core.llm": "llm",
    "src.core.ml": "llm",
    "src.core.tool_broker": "tool_broker",
    "src.core.tool_broker.ap_mcp_registry": "shared",  # Pure data types (enums+dataclasses), zero project deps -- SP-DSM-015 dag 1
    "src.core.sandbox": "tool_broker",
    "src.workers": "worker",
    "src.workers.calendar_sync_worker": "integrations",  # SP-DSM-013: extern kalender-sync, geen Dramatiq actor
    "src.workers.scheduler": "agent_runtime",  # SP-DSM-013: taakplanner -- schedules agent_runtime work
    "src.core.workers": "worker",
    "src.core.workers.tenant_context": "shared",  # ContextVar + single-tenant fallback resolver -- pure foundation
    "src.core.actors": "worker",
    "src.core.actors.gdpr_purge": "integrations",  # SP-DSM-013: GDPR compliance actor -- integrations concern
    "src.core.jobs": "worker",  # SP-DSM-013: jobs dir stays worker (alle 6 files importeren non-infra concerns)
    "src.core.tasks": "worker",
    "src.core.tasks.cva_tasks": "agent_runtime",  # SP-DSM-013: CVA-conversatietaken -- agent_runtime concern
    "src.core.tasks.workflow_tasks": "agent_runtime",  # SP-DSM-014: runt AutonomousAgent = agent_runtime concern
    "src.core.tasks.eigen_loop": "shared",  # Keten B nazorg B: poolloze-engine-helper voor actors -- infra, importeert alleen sqlalchemy en lazy db_manager (shared); anders +1 Ce voor cva_tasks (agent_runtime -> worker)
    "src.core.procedures": "domain_pack",
    "src.core.procedures.models": "shared",  # SQLAlchemy ORM model definitions -- foundational data, like governance.models + workflow.models
    "src.core.company": "domain_pack",
    "src.core.focus_builder": "integrations",  # SP-DSM-016 dag 3: importeert activepieces direct
    "src.core.subagents": "domain_pack",
    "src.core.prediction": "domain_pack",
    "src.core.experimentation": "domain_pack",
    "src.core.evaluation": "integrations",  # SP-DSM-016 dag 3: hybrid_search importeert dit; evaluation->integrations sluit terug-kant
    "src.core.autonomous_workflow": "domain_pack",
    "src.core.generation": "domain_pack",
    "src.core.conversations": "shared",  # SP-DSM-016 dag 2: sluit governance->domain_pack (dsar_service lazy import)
    "src.core.feature_flags": "domain_pack",
    "src.core.api": "core_api",
    # NOTE: SOURCE_DIRS intentionally not updated for database.database and resilience.
    # Files are scanned as infra-source; their import-targets are classified as shared.
    # This asymmetry is by design: shared = Ce-neutral foundation for measurement purposes.
    # test_shared_fan_out_is_zero is unaffected because SOURCE_DIRS["shared"] is unchanged.
    "src.core.database.database": "shared",  # Base/AsyncSession/db_manager -- ADR-004 RLS foundation
    "src.core.database": "infra",
    "src.core.noodstop": "infra",  # noodstop per klant (ADR-036 OP-03): leest een tabel; elke deur (broker, Council, workflow, taken) roept hem aan, dus een LAGERE laag dan zijn aanroepers
    "src.core.caching": "infra",
    "src.core.resilience": "shared",  # circuit_breaker+retry_policy -- pure infra, zero business imports
    "src.core.monitoring": "infra",
    "src.core.monitoring.drift_detection": "agent_runtime",
    "src.core.monitoring.dashboard": "agent_runtime",
    "src.core.monitoring.agent_circuit_metrics": "agent_runtime",
    "src.core.monitoring.vibe_monitoring": "integrations",  # websocket monitor = integrations
    "src.core.observability.tracing": "shared",
    "src.core.observability": "infra",
    "src.core.observability.audit_logger": "domain_pack",
    "src.core.observability.evaluation_repository": "domain_pack",
    "src.core.observability.alert_notification_bridge": "integrations",  # bridges alerts to notification channels -- integrations concern
    "src.core.scheduling": "infra",
    "src.core.scheduling.voice": "agent_runtime",
    "src.core.scheduling.agents": "agent_runtime",
    "src.core.scheduling.api.voice_routes": "agent_runtime",
    "src.core.scheduling.memory_consolidation_job": "agent_runtime",
    "src.core.scheduling.webhooks.handlers": "integrations",  # SP-DSM-013: webhook-afhandeling -- integrations concern (was "worker")
    "src.core.infrastructure": "infra",
    "src.core.startup": "infra",
    "src.core.engine": "infra",
    "src.core.config.feature_flags": "infra",
    "src.core.config": "shared",
    "src.core.repositories": "infra",
    "src.core.di": "shared",
    "src.core.shared": "shared",
    "src.core.shared.datetime_utils": "shared.time",  # SP-DSM-021 dag 3: datetime utilities -- pure stdlib, Ce=0
    "src.core.shared.unicode_utils": "shared.utils",  # SP-DSM-021 dag 4: string utilities -- pure stdlib, Ce=0
    "src.core.shared.unicode_logging": "shared.utils",  # SP-DSM-021 dag 4: logging setup -- pure stdlib, Ce=0
    # NOTE: docker_utils stays in shared -- src.core.shared.config imports it (intra-shared dep)
    "src.core.shared.ai_act_types": "shared.types",  # SP-DSM-021 dag 5: AI Act type definitions -- pure stdlib, Ce=0
    "src.core.shared.consent_categories": "shared.types",  # SP-DSM-021 dag 5: consent category enums -- pure stdlib, Ce=0
    # NOTE: interfaces.py stays in shared -- Ce=2 (imports src.core.types + src.core.shared.agent_context)
    "src.core.exceptions": "shared",
    "src.core.schemas": "shared",
    "src.core.base": "shared",
    "src.core.templates": "shared",
    "src.core.logging": "shared",
    "src.core.typing": "shared",
    "src.core.protocol": "agent_runtime",  # agent communication protocols -- agent_runtime concern (SP-DSM-010)
    "src.core.contracts": "shared",
    "src.core.utils": "shared",
    "src.core.models": "infra",
    "src.core.metrics": "infra",
    "src.ml": "domain_pack",
    "src.api": "core_api",
    "src.services": "agent_runtime",
    "src.core.activepieces.indexer": "agent_runtime",  # imports memory_manager (agent_runtime) -- reclassified (SP-DSM-010)
    "src.core.activepieces": "integrations",
    "src.core.integrations": "integrations",
    "src.core.connectors": "integrations",
    "src.core.communication": "integrations",
    "src.core.notifications": "integrations",
    "src.core.events.handlers": "agent_runtime",  # event handlers wire into agent_runtime logic (SP-DSM-010)
    "src.core.events": "integrations",
    "src.core.events.pubsub_manager": "infra",  # Redis pub/sub primitive -- stays in SOURCE_DIRS['integrations'] but classifies as infra (like resilience)
    "src.core.websocket": "integrations",
    "src.core.collaboration": "agent_runtime",  # task_distributor + agent mesh = agent coordination (SP-DSM-010)
    "src.core.session": "integrations",
    "src.core.i18n": "integrations",
    "src.core.translations": "integrations",
    "src.core.knowledge": "shared",  # SP-DSM-016 dag 3: alleen caching/database/shared imports; content_generator->knowledge wordt domain_pack->shared
    "src.core.memory": "agent_runtime",
    "src.domains.memory": "agent_runtime",
    "src.domains.flows": "agent_runtime",
    "src.domains.agentic": "agent_runtime",
    "src.domains.canvas": "domain_pack",
    "src.domains.documents": "domain_pack",
    "src.domains.projects": "domain_pack",
    "src.domains.notifications": "integrations",
    "src.domains.tasks": "agent_runtime",  # AGENTIC-COPILOT-TAAKBEHEER: agentic task layer
    "src.domains.tasks.models": "shared",  # Task ORM model definitions -- foundational data (cf. workflow.models, procedures.models)
    # NOTE: MODULE_MAP=shared, SOURCE_DIRS blijft in agent_runtime -- zelfde asymmetrie als
    # database.database/resilience/observability.tracing (zie regels 74-77). container.py heeft
    # lazy src.core.ai.* imports die AST scanner oppikt; die Ce telt als agent_runtime Ce.
    # MODULE_MAP=shared zorgt dat imports NAAR container tellen als ->shared (niet ->agent_runtime),
    # waardoor domain_pack->agent_runtime backward coupling via container verdwijnt (SP-DSM-014).
    "src.core.container": "shared",
    "src.core.dependencies": "core_api",
    "src.config": "shared",
    "src.main": "core_api",
    "src.core.analytics": "integrations",
    "src.core.search": "integrations",
    "src.core.storage": "integrations",
}

SOURCE_DIRS = {
    "tenancy": ["src/core/middleware", "src/core/ratelimit"],
    "auth": ["src/core/auth", "src/core/security", "src/core/hardening"],
    "governance": [
        # governance/: enumerate individually to exclude event_handlers.py (-> worker)
        # and dsar_notifications.py (-> integrations) -- SP-DSM-011 governance_worker pattern
        "src/core/governance/__init__.py",
        "src/core/governance/accuracy_monitor.py",
        "src/core/governance/ai_act_classifier.py",
        "src/core/governance/ai_transparency_service.py",
        "src/core/governance/alert_manager.py",
        "src/core/governance/attribution.py",
        "src/core/governance/audit.py",
        "src/core/governance/authority_reporting.py",
        "src/core/governance/compliance_aggregation.py",
        "src/core/governance/compliance_guardian.py",
        "src/core/governance/compliance_score.py",
        "src/core/governance/cookie_consent.py",
        "src/core/governance/dsar_service.py",
        "src/core/governance/gdpr_enforcer.py",
        "src/core/governance/governance_helper.py",
        "src/core/governance/hash_chain.py",
        "src/core/governance/incident_service.py",
        "src/core/governance/lawful_basis_registry.py",
        "src/core/governance/learning_audit.py",
        "src/core/governance/ml_strategy.py",
        "src/core/governance/model_cards.py",
        "src/core/governance/model_provenance.py",
        "src/core/governance/models.py",
        "src/core/governance/oversight_gate.py",
        "src/core/governance/policy_engine.py",
        "src/core/governance/prana_guard.py",
        "src/core/governance/public_docs.py",
        "src/core/governance/quality_management.py",
        "src/core/governance/rate_limiter.py",
        "src/core/governance/rbac_step_enforcer.py",
        "src/core/governance/retention_cleanup.py",
        "src/core/governance/risk_register.py",
        "src/core/governance/staleness_detector.py",
        "src/core/governance/governance_agent",
        "src/core/governance/repositories",
        "src/core/governance/services",
        "src/core/governance_v2",
        "src/core/ethics",
        "src/core/audit",
        "src/core/traceability",
    ],
    "agent_runtime": [
        "src/core/agents",
        "src/core/als",
        "src/core/services",
        "src/core/workflow",
        "src/core/learning",
        "src/core/orchestrator",
        "src/core/runtime",
        "src/core/strategy",
        "src/core/routing",
        "src/core/semantic_router",
        "src/core/awareness",
        "src/core/intelligence",
        "src/core/emergence",
        "src/core/optimization",
        "src/domains/memory",
        "src/domains/flows",
        "src/domains/agentic",
        "src/domains/tasks",  # AGENTIC-COPILOT-TAAKBEHEER: agentic task layer
        "src/core/ai",
        "src/core/copilot",
        "src/core/autonomy",
        "src/core/memory",
        "src/services",
        "src/core/scheduling/voice",
        "src/core/scheduling/agents",
        "src/core/monitoring/dashboard.py",
        "src/core/monitoring/drift_detection.py",
        "src/core/monitoring/agent_circuit_metrics.py",
        "src/core/scheduling/api/voice_routes.py",
        "src/core/scheduling/memory_consolidation_job.py",
        "src/core/container.py",
        "src/core/collaboration",  # task_distributor = agent coordination (SP-DSM-010)
        "src/core/events/handlers",  # event handlers wire into agent_runtime logic (SP-DSM-010)
        "src/core/events/learning_event_wiring.py",  # wires learning event handlers = agent_runtime concern (SP-DSM-010)
        "src/core/activepieces/indexer.py",  # imports memory_manager = agent_runtime dependency (SP-DSM-010)
        "src/core/protocol",  # agent communication protocols = agent_runtime concern (SP-DSM-010)
        "src/core/tasks/cva_tasks.py",  # SP-DSM-013: CVA-conversatietaken -- agent_runtime concern
        "src/workers/scheduler.py",  # SP-DSM-013: taakplanner -- schedules agent_runtime actors
        "src/core/tasks/workflow_tasks.py",  # SP-DSM-014: runt AutonomousAgent = agent_runtime concern
    ],
    "llm": ["src/core/llm", "src/core/ml"],
    "tool_broker": [
        # src/core/tool_broker enumereren: service.py heeft lazy agent_runtime import
        # (src.core.als.agents.loader op regel 147 in functie-body) -- SP-DSM-014 ghost
        "src/core/tool_broker/__init__.py",
        "src/core/tool_broker/ap_mcp_registry.py",
        "src/core/tool_broker/audit_repository.py",
        "src/core/tool_broker/audit_utils.py",
        "src/core/tool_broker/clients.py",
        "src/core/tool_broker/config.py",
        "src/core/tool_broker/dependencies.py",
        "src/core/tool_broker/exceptions.py",
        "src/core/tool_broker/health.py",
        "src/core/tool_broker/hitl_notifier.py",
        "src/core/tool_broker/hitl_repository.py",
        "src/core/tool_broker/hitl_store.py",
        "src/core/tool_broker/local_registry.py",
        "src/core/tool_broker/main.py",
        "src/core/tool_broker/mcp_client.py",
        "src/core/tool_broker/models.py",
        "src/core/tool_broker/permission_manager.py",
        "src/core/tool_broker/resilience.py",
        "src/core/tool_broker/risk_classifier.py",
        "src/core/tool_broker/router.py",
        "src/core/tool_broker/schemas.py",
        # service.py -> ghost: lazy src.core.als import op regel 147 (SP-DSM-014)
        # test_tools.py -> auto-skipped door test-pad filter
        "src/core/sandbox",
    ],
    "worker": [
        # SP-DSM-013: src/workers/ enumereren (calendar_sync_worker -> integrations,
        #   scheduler -> agent_runtime; workflow_worker blijft worker maar zit niet in SOURCE_DIRS)
        "src/workers/__init__.py",
        # src/workers/actors.py -> ghost: importeert 3x copilot + cva_tasks (agent_runtime) -- SP-DSM-014
        # src/workers/scheduler.py -> agent_runtime SOURCE_DIRS (SP-DSM-013)
        # src/workers/workflow_worker.py -> worker MODULE_MAP, niet in SOURCE_DIRS (ghost worker)
        # src/core/actors/__init__.py bestaat niet -- alleen gdpr_purge.py (-> integrations)
        # src/core/jobs/ blijft "worker" in MODULE_MAP; alle 6 bestanden importeren non-infra concerns
        # SP-DSM-013: src/core/tasks/ enumereren (cva_tasks.py -> agent_runtime)
        # src/core/tasks/__init__.py bestaat niet -- alleen background_manager, cva_tasks, workflow_tasks
        "src/core/tasks/background_manager.py",
        # src/core/tasks/workflow_tasks.py -> agent_runtime SOURCE_DIRS (SP-DSM-014)
        # src/core/scheduling/webhooks/handlers.py -> integrations SOURCE_DIRS
    ],
    "domain_pack": [
        "src/core/ai_quality",
        "src/core/procedures",
        # src/core/company enumereren: external_agent_bridge.py + template_service.py
        # importeren agent_runtime (agents.base_agent / agents.models) -- SP-DSM-014 ghost
        "src/core/company/__init__.py",
        "src/core/company/agent_mappings.py",
        "src/core/company/board_service.py",
        "src/core/company/company_service.py",
        "src/core/company/context.py",
        "src/core/company/department_service.py",
        "src/core/company/e2e_seed.py",
        # external_agent_bridge.py -> ghost: from src.core.agents.base_agent (SP-DSM-014)
        "src/core/company/external_agent_service.py",
        "src/core/company/feature_flags.py",
        "src/core/company/goal_alignment.py",
        "src/core/company/goal_service.py",
        "src/core/company/models.py",
        "src/core/company/pack_activation.py",
        "src/core/company/schemas.py",
        "src/core/company/sector_departments.py",
        "src/core/company/seed_templates.py",
        # template_service.py -> ghost: from src.core.agents.models (SP-DSM-014)
        # focus_builder -> ghost: reclassificeerd naar integrations -- SP-DSM-016 dag 3
        # (service.py importeert activepieces direct)
        "src/core/subagents",
        "src/core/prediction",
        "src/core/experimentation",
        "src/core/evaluation",  # MODULE_MAP: integrations -- asymmetrisch patroon: SOURCE_DIRS blijft in domain_pack (SP-DSM-016 dag 3)
        # src/core/autonomous_workflow enumereren: bootstrap.py importeert
        # src.core.services.training_service (agent_runtime) -- SP-DSM-014 ghost
        "src/core/autonomous_workflow/__init__.py",
        "src/core/autonomous_workflow/attention.py",
        # bootstrap.py -> ghost: from src.core.services.training_service (SP-DSM-014)
        "src/core/autonomous_workflow/config.py",
        "src/core/autonomous_workflow/curriculum.py",
        "src/core/autonomous_workflow/dynamic/encoder.py",
        "src/core/autonomous_workflow/dynamic/model.py",
        "src/core/autonomous_workflow/dynamic/training.py",
        "src/core/autonomous_workflow/feedback.py",
        "src/core/autonomous_workflow/feedback_service.py",
        "src/core/autonomous_workflow/models.py",
        "src/core/autonomous_workflow/models/__init__.py",
        "src/core/autonomous_workflow/models/base.py",
        "src/core/autonomous_workflow/models/learning_experience.py",
        "src/core/autonomous_workflow/models/workflow_experience.py",
        "src/core/autonomous_workflow/modular_training.py",
        "src/core/autonomous_workflow/orchestrator.py",
        "src/core/autonomous_workflow/routes.py",
        "src/core/autonomous_workflow/schemas.py",
        "src/core/autonomous_workflow/training.py",
        "src/core/autonomous_workflow/training/__init__.py",
        "src/core/autonomous_workflow/training/nn_models.py",
        "src/core/autonomous_workflow/training_scheduler.py",
        "src/core/autonomous_workflow/unified_training.py",
        "src/core/generation",
        # conversations -> ghost: reclassificeerd naar shared -- SP-DSM-016 dag 2
        "src/core/feature_flags",
        "src/domains/canvas",
        "src/domains/documents",
        "src/domains/projects",
        "src/ml",
    ],
    "core_api": [
        "src/core/api",
        "src/api",
        "src/core/dependencies.py",
        # Scheduling API route-handlers (verplaatst van infra -- route-handlers horen bij core_api)
        "src/core/scheduling/api/__init__.py",
        "src/core/scheduling/api/conflict_routes.py",
        "src/core/scheduling/api/integration_routes.py",
        "src/core/scheduling/api/mobile_routes.py",
        "src/core/scheduling/api/nlp_routes.py",
        "src/core/scheduling/api/partner_routes.py",
        "src/core/scheduling/api/routes.py",
        "src/core/scheduling/api/smart_routes.py",
        "src/core/scheduling/api/webhook_routes.py",
        "src/core/scheduling/api/websocket.py",
    ],
    "infra": [
        "src/core/database",
        "src/core/caching",
        "src/core/resilience",
        "src/core/monitoring/__init__.py",
        "src/core/monitoring/advanced_analytics.py",
        "src/core/monitoring/advanced_metrics.py",
        "src/core/monitoring/alert_system.py",
        "src/core/monitoring/cva_metrics.py",
        "src/core/monitoring/health_checks.py",
        "src/core/monitoring/healing_metrics.py",
        "src/core/monitoring/log_analyzer.py",
        "src/core/monitoring/metrics_collector.py",
        "src/core/monitoring/middleware.py",
        "src/core/monitoring/mock_usage_detector.py",
        "src/core/monitoring/ooda_metrics.py",
        "src/core/monitoring/pack_metrics.py",
        "src/core/monitoring/performance_analytics.py",
        "src/core/monitoring/performance_monitor.py",
        "src/core/monitoring/performance_profiler.py",
        "src/core/monitoring/prometheus_metrics.py",
        "src/core/monitoring/security_metrics.py",
        "src/core/monitoring/tool_broker_tracing.py",
        "src/core/monitoring/trace.py",
        "src/core/monitoring/tracing.py",
        # observability: enumerate individually to exclude alert_notification_bridge (-> integrations)
        "src/core/observability/__init__.py",
        "src/core/observability/alert_manager.py",
        "src/core/observability/audit_logger.py",
        "src/core/observability/compliance_metrics.py",
        "src/core/observability/evaluation_repository.py",
        "src/core/observability/logging.py",
        "src/core/observability/metrics.py",
        "src/core/observability/pack_metrics.py",
        "src/core/observability/tenant_metrics.py",
        "src/core/observability/tracing.py",
        "src/core/scheduling/conflicts",
        "src/core/scheduling/integrations",
        "src/core/scheduling/nlp",
        "src/core/scheduling/partners",
        "src/core/scheduling/services",
        "src/core/scheduling/smart",
        # scheduling/webhooks: enumerate individually to exclude handlers (-> integrations, SP-DSM-013)
        "src/core/scheduling/webhooks/__init__.py",
        "src/core/scheduling/webhooks/models.py",
        "src/core/scheduling/webhooks/registration_service.py",
        "src/core/scheduling/webhooks/repository.py",
        "src/core/scheduling/__init__.py",
        "src/core/scheduling/config.py",
        "src/core/scheduling/models.py",
        "src/core/scheduling/repository.py",
        "src/core/scheduling/schemas.py",
        "src/core/infrastructure",
        "src/core/startup",
        "src/core/engine",
        "src/core/config",
        "src/core/repositories",
        "src/core/di",
        "src/core/models",
    ],
    "shared": [
        "src/core/shared",
        "src/core/conversations",  # SP-DSM-016 dag 2: reclassificeerd van domain_pack (alleen database.Base import)
        "src/core/exceptions",
        "src/core/schemas",
        "src/core/base",
        "src/core/templates",
        "src/core/logging",
        "src/core/typing",
        "src/core/contracts",
        "src/core/utils",
    ],
    "shared.time": [  # SP-DSM-021 dag 3: datetime utilities sub-laag (Ce=0 invariant)
        "src/core/shared/datetime_utils.py",
    ],
    "shared.utils": [  # SP-DSM-021 dag 4: string/logging utilities sub-laag (Ce=0 invariant)
        "src/core/shared/unicode_utils.py",
        "src/core/shared/unicode_logging.py",
        # NOTE: docker_utils excluded -- intra-shared dep from config.py, stays in shared
    ],
    "shared.types": [  # SP-DSM-021 dag 5: type/enum definitions sub-laag (Ce=0 invariant)
        "src/core/shared/ai_act_types.py",
        "src/core/shared/consent_categories.py",
        # NOTE: interfaces.py excluded -- Ce=2 (imports src.core.types + src.core.shared.agent_context)
    ],
    "integrations": [
        # activepieces: enumerate individually to exclude indexer.py (-> agent_runtime, SP-DSM-010)
        "src/core/activepieces/__init__.py",
        "src/core/activepieces/catalog_syncer.py",
        "src/core/activepieces/client.py",
        "src/core/activepieces/dependencies.py",
        "src/core/activepieces/models.py",
        "src/core/activepieces/repositories.py",
        "src/core/activepieces/schemas.py",
        "src/core/activepieces/service.py",
        "src/core/activepieces/tenant_utils.py",
        "src/core/activepieces/transformer.py",
        "src/core/activepieces/validator.py",
        "src/core/integrations",
        # protocol removed: reclassified to agent_runtime (SP-DSM-010)
        "src/core/connectors",
        "src/core/communication",
        "src/core/notifications",
        # events: enumerate individually to exclude handlers/ subdir and learning_event_wiring.py (both -> agent_runtime, SP-DSM-010)
        "src/core/events/__init__.py",
        "src/core/events/consumer.py",
        "src/core/events/department_activation_handler.py",
        "src/core/events/handlers.py",
        "src/core/events/publisher.py",
        "src/core/events/pubsub_manager.py",
        "src/core/events/signal_router.py",
        "src/core/websocket",
        # collaboration removed: reclassified to agent_runtime (SP-DSM-010)
        "src/core/session",
        "src/core/i18n",
        "src/core/translations",
        "src/core/knowledge",
        "src/core/analytics",
        "src/core/search",
        "src/core/storage",
        # NOTE: vibe_monitoring reclassified to integrations (websocket auth monitor).
        # MODULE_MAP entry "src.core.monitoring.vibe_monitoring": "integrations" must match.
        "src/core/monitoring/vibe_monitoring.py",
        # alert_notification_bridge bridges observability to notification channels -- integrations concern
        "src/core/observability/alert_notification_bridge.py",
        "src/core/governance/dsar_notifications.py",  # SP-DSM-011: governance_worker pattern
        "src/core/governance/event_handlers.py",  # SP-DSM-012: event-bus adapter, niet worker
        # SP-DSM-016 dag 3: focus_builder reclassificeerd van domain_pack (activepieces direct import)
        "src/core/focus_builder/models.py",
        "src/core/focus_builder/schemas.py",
        "src/core/focus_builder/service.py",
        "src/core/focus_builder/validators.py",
        # repositories.py -> ghost: from src.domains.flows.models (SP-DSM-014, blijft van kracht)
        # SP-DSM-013: worker reclassificaties
        "src/workers/calendar_sync_worker.py",  # extern kalender-sync, geen actor
        # src/core/actors/__init__.py bestaat niet -- geen double-counting risico
        "src/core/actors/gdpr_purge.py",  # GDPR compliance actor
        "src/core/scheduling/webhooks/handlers.py",  # webhook-afhandeling
    ],
}

MODULES = [
    "tenancy",
    "auth",
    "governance",
    "agent_runtime",
    "llm",
    "tool_broker",
    "worker",
    "domain_pack",
    "core_api",
    "infra",
    "shared",
    "shared.time",  # SP-DSM-021 dag 3: datetime utilities sub-laag
    "shared.utils",  # SP-DSM-021 dag 4: string/logging utilities sub-laag
    "shared.types",  # SP-DSM-021 dag 5: type/enum definitions sub-laag
    "integrations",
]


def classify(mod_str: str) -> str | None:
    best, best_len = None, 0
    for prefix, dsm in MODULE_MAP.items():
        if mod_str == prefix or mod_str.startswith(prefix + "."):
            if len(prefix) > best_len:
                best, best_len = dsm, len(prefix)
    return best


def _file_to_module(path: Path) -> str:
    """Convert a file path to a Python module string (e.g. src.core.agents.foo)."""
    parts = path.with_suffix("").parts
    try:
        return ".".join(parts[list(parts).index("src") :])
    except ValueError:
        return ""


def _resolve_relative_import(path: Path, level: int, module: str) -> str:
    """Resolve a relative import to its absolute module name.

    Implements CPython _resolve_name: go up (level-1) packages from the file's
    package, then append module. Example:
      path = src/core/agents/generated/foo.py, level=4, module=core.llm.bar
      pkg  = src.core.agents.generated
      3 steps up: src.core.agents -> src.core -> src
      result = src.core.llm.bar
    """
    pkg = ".".join(_file_to_module(path).rsplit(".", 1)[:-1])
    if not pkg:
        return module
    base = pkg
    for _ in range(level - 1):
        base = base.rpartition(".")[0]
        if not base:
            return module
    return f"{base}.{module}" if module else base


def _collect_type_checking_nodes(tree: ast.Module) -> set[int]:
    """Return id() of all AST nodes inside TYPE_CHECKING blocks.

    NOTE: Must receive the same parsed tree object as the caller uses for
    ast.walk(). id() stability is guaranteed only within a single ast.parse()
    lifetime -- do NOT call this with a separately re-parsed tree.

    TYPE_CHECKING imports are annotation-only and never executed at runtime.
    Counting them as fan-out would produce false circular-dep reports.
    Covers both `if TYPE_CHECKING:` and `if typing.TYPE_CHECKING:` forms.
    """
    tc_ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        is_tc = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute)
            and test.attr == "TYPE_CHECKING"
            and isinstance(test.value, ast.Name)
            and test.value.id == "typing"
        )
        if is_tc:
            for child in ast.walk(node):
                tc_ids.add(id(child))
    return tc_ids


#: Bestanden waarvan de `import x` op moduleniveau een REGISTRATIE is en geen afhankelijkheid.
#: Sleutel `bestand::<module>` (alleen moduleniveau; een import in een functie telt altijd), met reden.
#: De uitzondering geldt per import alleen als het DOEL een SQLAlchemy-model definieert (zie
#: `_definieert_model`); een `from x import y`, een niet-modelimport of een import in een functie
#: in hetzelfde bestand telt dus WEL. Gedateerd 2026-10-22 (brief dsm-meter-telt-ook-import-x).
MODEL_REGISTRATIE_BESTANDEN: dict[str, str] = {
    "src/core/database/import_all_models.py::<module>": (
        "side-effect registratie van modellen voor Alembic en create_all: de database-laag moet "
        "alle modellen kennen om hun metadata te vullen; dat is geen runtime-afhankelijkheid"
    ),
}


def _repo_wortel_en_pad(path: Path) -> tuple[Path, str]:
    """(repo-wortel, pad vanaf `src/` met schuine strepen): de scan krijgt relatieve en absolute paden."""
    delen = list(path.parts)
    if "src" not in delen:
        return Path("."), path.as_posix()
    i = delen.index("src")
    wortel = Path(*delen[:i]) if i else Path(".")
    return wortel, "/".join(delen[i:])


def _module_bestand(module: str, wortel: Path) -> Path | None:
    basis = wortel / Path(*module.split("."))
    for kandidaat in (basis.with_suffix(".py"), basis / "__init__.py"):
        if kandidaat.exists():
            return kandidaat
    return None


def _definieert_model(module: str, wortel: Path) -> bool:
    """Definieert dit doel een SQLAlchemy-model: een klasse met `__tablename__` of met basis `Base`?

    Twee structurele kenmerken van een declaratief model. Een pydantic-model (`BaseModel`), een
    Enum of een pakket dat alleen her-exporteert voldoet niet en telt dus als gewone afhankelijkheid.
    """
    bestand = _module_bestand(module, wortel)
    if bestand is None:
        return False
    try:
        boom = ast.parse(bestand.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return False
    for klasse in ast.walk(boom):
        if not isinstance(klasse, ast.ClassDef):
            continue
        for basis in klasse.bases:
            naam = (
                basis.id
                if isinstance(basis, ast.Name)
                else basis.attr
                if isinstance(basis, ast.Attribute)
                else ""
            )
            if naam == "Base":
                return True
        for stap in klasse.body:
            if isinstance(stap, ast.Assign) and any(
                isinstance(doel, ast.Name) and doel.id == "__tablename__" for doel in stap.targets
            ):
                return True
    return False


def _is_model_registratie(path: Path, node: ast.Import, tree: ast.Module, module: str) -> bool:
    """Is dit `import <model-module>` op moduleniveau in een bestand uit MODEL_REGISTRATIE_BESTANDEN?"""
    wortel, pad = _repo_wortel_en_pad(path)
    if f"{pad}::<module>" not in MODEL_REGISTRATIE_BESTANDEN:
        return False
    return node in tree.body and _definieert_model(module, wortel)


def scan_module(
    source_name: str, dirs: list[str], *, unique_pairs: bool = False
) -> tuple[collections.Counter[str], int, collections.Counter[str]]:
    """Scan a DSM module's outgoing runtime imports.

    Args:
        source_name: DSM bucket being scanned.
        dirs: source dirs belonging to that bucket.
        unique_pairs: how to COUNT coupling.

            False (default, historical): count every import STATEMENT. Keeps the
            historical series comparable -- core_api went 1139 -> 800 on this
            scale (DSM-FUTUREPROOF-AUDIT-v6.1, SPRINT_TRACKER) -- and keeps the
            instability (Ce/Ca) figures and the other DSM tests unchanged.

            True: count unique (file, target-module) pairs, i.e. "how many files
            know about module X". Introduced 2026-08-01 (OP-11 follow-up, Rakesh
            GO) for the fan-out budget gate, because the statement count is
            gameable: two `from src.core.auth.api_deps import ...` lines in one
            file score 2, and merging them into one line scores 1 without
            changing a single dependency. That loophole was used twice under
            deadline pressure during OP-11 to stay inside the ceiling -- a clear
            sign the metric measured formatting instead of coupling. It also
            cannot distinguish one facade importing 17 symbols from a module
            (a deliberate chokepoint, ADR-033) from 17 routers importing one
            each (scattered coupling); both score 17.
    """
    counts: collections.Counter[str] = collections.Counter()
    files = 0
    unclassified: collections.Counter[str] = collections.Counter()
    seen_pairs: set[tuple[str, str]] = set()
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        paths = [p] if p.is_file() else list(p.rglob("*.py"))
        for path in paths:
            parts = path.parts
            if any("test" in part.lower() for part in parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                continue
            files += 1
            # NOTE: tc_ids computed from the same tree -- do not re-parse between calls
            tc_ids = _collect_type_checking_nodes(tree)
            for node in ast.walk(tree):
                if id(node) in tc_ids:
                    continue
                if isinstance(node, ast.Import):
                    # `import x` en `import x as y` tellen als `from x import y`. Tot 2026-10-22
                    # zag de meter ze niet (100 regels onder src/): zie de test
                    # test_dsm_meter_telt_import_x.
                    mods = []
                    for alias in node.names:
                        imported = alias.name
                        if imported.startswith("src.core.src."):
                            imported = "src." + imported[len("src.core.src.") :]
                        if not imported.startswith("src."):
                            continue
                        if _is_model_registratie(path, node, tree, imported):
                            continue
                        mods.append(imported)
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        if not node.module:
                            continue
                        mod = node.module
                        if mod.startswith("src.core.src."):
                            mod = "src." + mod[len("src.core.src.") :]
                        if not mod.startswith("src."):
                            continue
                    elif node.module:
                        mod = _resolve_relative_import(path, node.level, node.module)
                        if not mod.startswith("src."):
                            continue
                    else:
                        continue
                    mods = [mod]
                else:
                    continue
                for mod in mods:
                    target = classify(mod)
                    if target is None:
                        unclassified[mod.split(".")[2] if mod.count(".") >= 2 else mod] += 1
                    elif target != source_name:
                        if unique_pairs:
                            pair = (path.as_posix(), target)
                            if pair in seen_pairs:
                                continue
                            seen_pairs.add(pair)
                        counts[target] += 1
    return counts, files, unclassified


def calculate_instability(module: str, exclude_shared: bool = True) -> dict[str, float | int]:
    """Robert Martin instability: I = Ce / (Ce + Ca).

    Ce = fan-out (efferent coupling): runtime imports going out from module.
    Ca = fan-in (afferent coupling): imports coming in to module from others.
    exclude_shared: exclude shared-bucket imports from Ce (foundation layer,
    importing from shared does not destabilize the importer).

    Returns dict with keys: instability (float), fan_out (int), fan_in (int).
    Returns instability=0.0 when Ce + Ca == 0 (isolated module edge case).
    """
    if module not in MODULES:
        raise ValueError(f"Unknown DSM module: {module!r}")

    ce_counts, _, _ = scan_module(module, SOURCE_DIRS.get(module, []))
    ce = sum(
        v
        for k, v in ce_counts.items()
        if not (exclude_shared and (k == "shared" or k.startswith("shared.")))
    )

    ca = 0
    for other_mod in MODULES:
        if other_mod == module:
            continue
        other_counts, _, _ = scan_module(other_mod, SOURCE_DIRS.get(other_mod, []))
        ca += other_counts.get(module, 0)

    total = ce + ca
    instability = ce / total if total > 0 else 0.0
    return {"instability": instability, "fan_out": ce, "fan_in": ca}


def main() -> None:
    fanout: dict[str, collections.Counter[str]] = {}
    file_counts: dict[str, int] = {}
    all_unclassified: collections.Counter[str] = collections.Counter()

    print("Scanning (test-bestanden uitgesloten)...")
    for mod in MODULES:
        dirs = SOURCE_DIRS.get(mod, [])
        c, f, unc = scan_module(mod, dirs)
        fanout[mod] = c
        file_counts[mod] = f
        all_unclassified.update(unc)
        total_fo = sum(c.values())
        print(f"  {mod:<16} {f:>4} bestanden  fan-out={total_fo}")

    short = {
        "tenancy": "tenancy",
        "auth": "auth",
        "governance": "gov",
        "agent_runtime": "agt_rt",
        "llm": "llm",
        "tool_broker": "tool",
        "worker": "worker",
        "domain_pack": "dom_pk",
        "core_api": "core_api",
        "infra": "infra",
        "shared": "shared",
        "shared.time": "sh.time",  # SP-DSM-021 dag 3
        "shared.utils": "sh.u",  # SP-DSM-021 dag 4
        "shared.types": "sh.typ",  # SP-DSM-021 dag 5
        "integrations": "integr",
    }
    hdr_labels = [short[m] for m in MODULES]
    col = 8
    hdr_w = 14

    print()
    print("=" * 80)
    print("GEWOGEN DSM MATRIX (werkelijke import-statements, test-files uitgesloten)")
    print("=" * 80)
    print(f"{'FROM-TO':>{hdr_w}}", end="")
    for h in hdr_labels:
        print(f"{h:>{col}}", end="")
    print("  | fan-OUT")
    print("-" * (hdr_w + col * len(MODULES) + 12))

    fan_in: collections.Counter[str] = collections.Counter()
    row_totals: dict[str, int] = {}
    for from_mod in MODULES:
        row = fanout[from_mod]
        total = sum(row.values())
        row_totals[from_mod] = total
        label = short[from_mod]
        print(f"{label:>{hdr_w}}", end="")
        for to_mod in MODULES:
            if from_mod == to_mod:
                print(f"{'--':>{col}}", end="")
            else:
                v = row.get(to_mod, 0)
                fan_in[to_mod] += v
                display = str(v) if v > 0 else "."
                print(f"{display:>{col}}", end="")
        print(f"  | {total:>7}")

    print("-" * (hdr_w + col * len(MODULES) + 12))
    print(f"{'fan-IN':>{hdr_w}}", end="")
    for m in MODULES:
        print(f"{fan_in[m]:>{col}}", end="")
    print()

    print()
    print("KOPPELINGSRANGLIJST")
    print(f"{'Module':<16} {'Files':>6} {'fan-OUT':>8} {'fan-IN':>8}  Oordeel")
    print("-" * 60)
    for m in sorted(MODULES, key=lambda x: row_totals[x] + fan_in[x], reverse=True):
        fo = row_totals[m]
        fi = fan_in[m]
        if fo >= 500 or fi >= 500:
            flag = "KRITIEK"
        elif fo >= 200 or fi >= 200:
            flag = "HOOG"
        elif fo >= 80 or fi >= 80:
            flag = "MEDIUM"
        elif fo >= 20 or fi >= 20:
            flag = "LAAG"
        else:
            flag = "minimaal"
        print(f"{m:<16} {file_counts[m]:>6} {fo:>8} {fi:>8}  {flag}")

    print()
    print("CIRCULAIRE DEPENDENCIES:")
    found = False
    for a in MODULES:
        for b in MODULES:
            if a >= b:
                continue
            ab = fanout[a].get(b, 0)
            ba = fanout[b].get(a, 0)
            if ab > 0 and ba > 0:
                sev = "KRITIEK" if (ab + ba) >= 100 else "MEDIUM" if (ab + ba) >= 20 else "LAAG"
                print(f"  [{sev}] {a} <-> {b}: {ab} heen / {ba} terug")
                found = True
    if not found:
        print("  Geen gevonden.")

    print()
    if all_unclassified:
        print(
            "Ongeclassificeerde src.core.* imports (top 10) -- toevoegen aan MODULE_MAP indien relevant:"
        )
        for mod, cnt in all_unclassified.most_common(10):
            print(f"  src.core.{mod}: {cnt}x")


def generate_html(output_path: str) -> None:
    """Generate violation-aware DSM HTML report to output_path."""
    import sys
    from datetime import datetime, timezone

    _repo_root = str(Path(__file__).parent.parent)
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)

    from scripts.dsm_contract_aware_analysis import scan_module_contract_aware
    from scripts.dsm_api_violation_finder import find_violations

    print("Scanning raw imports...")
    raw_matrix: list[list[int]] = []
    fan_in: list[int] = [0] * len(MODULES)
    raw_fanout: list[int] = []
    file_counts: list[int] = []
    all_unc: collections.Counter[str] = collections.Counter()

    for mod in MODULES:
        dirs = SOURCE_DIRS.get(mod, [])
        counts, nfiles, unc = scan_module(mod, dirs)
        row = [counts.get(t, 0) for t in MODULES]
        raw_matrix.append(row)
        raw_fanout.append(sum(row))
        file_counts.append(nfiles)
        for j, v in enumerate(row):
            fan_in[j] += v
        all_unc.update(unc)

    print("Classifying imports (contract-aware)...")
    viol_matrix: list[list[int]] = []
    ok_matrix: list[list[int]] = []

    for mod in MODULES:
        dirs = SOURCE_DIRS.get(mod, [])
        ca, _ = scan_module_contract_aware(mod, dirs)
        viol_matrix.append([ca["violation"].get(t, 0) for t in MODULES])
        ok_matrix.append([ca["allowed"].get(t, 0) + ca["exempt"].get(t, 0) for t in MODULES])

    print("Finding ADR-033 violations...")
    violations_raw = find_violations()
    by_file: dict[str, int] = {}
    for vpath, _, _ in violations_raw:
        rel = str(vpath.relative_to(Path(__file__).parent.parent)).replace("\\", "/")
        by_file[rel] = by_file.get(rel, 0) + 1
    top_files = sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]
    total_v = len(violations_raw)
    v_ceil = 0

    gen_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    short = [
        "ten",
        "auth",
        "gov",
        "agt",
        "llm",
        "tool",
        "wkr",
        "dom",
        "api",
        "inf",
        "shr",
        "sh.t",
        "sh.u",
        "sh.typ",
        "int",
    ]

    rows_html = []
    for i, from_mod in enumerate(MODULES):
        cells = []
        for j in range(len(MODULES)):
            if i == j:
                cells.append('<td class="diag">--</td>')
                continue
            raw = raw_matrix[i][j]
            viol = viol_matrix[i][j]
            ok = ok_matrix[i][j]
            if raw == 0:
                cells.append('<td class="zero">.</td>')
            elif viol > 0:
                sup = f'<sup class="aok">{ok}</sup>' if ok > 0 else ""
                cells.append(
                    f'<td class="viol" title="{viol}v {ok}ok">'
                    f'<span class="vnum">{viol}</span>{sup}</td>'
                )
            elif ok > 0:
                cells.append(f'<td class="ok" title="0v {ok}ok">{raw}</td>')
            else:
                cells.append(f'<td class="raw">{raw}</td>')
        fo = raw_fanout[i]
        fi = fan_in[i]
        inst = f"{fo / (fi + fo):.2f}" if (fi + fo) > 0 else "0.00"
        rows_html.append(
            f"<tr><th>{from_mod}</th>{''.join(cells)}"
            f'<td class="fo">{fo}</td><td class="inst">{inst}</td></tr>'
        )
    fi_cells = "".join(f"<td>{fan_in[j]}</td>" for j in range(len(MODULES)))
    matrix_tab = (
        '<div class="badges">'
        '<span class="badge-red">ROODcel = echte violation</span>'
        '<span class="badge-green">GROENcel = facade OK (ADR-033)</span>'
        '<span class="badge-grey">GRIJScel = geen classificatie</span>'
        "</div>"
        '<table class="dsm"><thead><tr><th>FROM\\TO</th>'
        + "".join(f"<th>{s}</th>" for s in short)
        + "<th>fan-OUT</th><th>I</th></tr></thead><tbody>"
        + "".join(rows_html)
        + f'<tr class="fi-row"><th>fan-IN</th>{fi_cells}<td></td><td></td></tr>'
        + "</tbody></table>"
    )

    vrows = "".join(
        f'<tr><td class="vf">{f}</td><td class="vc">{c}</td></tr>' for f, c in top_files
    )
    trend_cls = "badge-red" if total_v >= v_ceil else "badge-green"
    trend_txt = (
        "BOVEN CEILING"
        if total_v > v_ceil
        else ("AT CEILING" if total_v == v_ceil else f"{v_ceil - total_v} onder ceiling")
    )
    violations_tab = (
        '<div class="badges">'
        f'<span class="badge-red">{total_v} echte violations</span>'
        f'<span class="badge-grey">ceiling: {v_ceil}</span>'
        f'<span class="{trend_cls}">{trend_txt}</span>'
        "</div>"
        "<h3>Top bestanden met violations</h3>"
        '<table class="vtable"><thead><tr><th>Bestand</th><th>Violations</th></tr></thead><tbody>'
        + vrows
        + "</tbody></table>"
        '<p class="note">Fix-patroon: verplaats verboden imports naar het domein\'s dependencies.py</p>'
    )

    circ_rows = []
    for ai, a in enumerate(MODULES):
        for bi in range(ai + 1, len(MODULES)):
            b = MODULES[bi]
            ab = raw_matrix[ai][bi]
            ba = raw_matrix[bi][ai]
            if ab > 0 and ba > 0:
                total = ab + ba
                av = viol_matrix[ai][bi] + viol_matrix[bi][ai]
                sev = "KRITIEK" if total >= 100 else "MEDIUM" if total >= 20 else "LAAG"
                scls = "sev-k" if sev == "KRITIEK" else "sev-m" if sev == "MEDIUM" else "sev-l"
                note = "facade OK" if av == 0 else f"{av} echte violations"
                circ_rows.append(
                    f'<tr><td class="{scls}">{sev}</td><td>{a}</td><td>{ab}</td>'
                    f"<td>{b}</td><td>{ba}</td><td>{note}</td></tr>"
                )
    circulaire_tab = (
        '<table class="vtable"><thead><tr><th>Ernst</th><th>Module A</th>'
        "<th>A-&gt;B</th><th>Module B</th><th>B-&gt;A</th><th>Oordeel</th></tr></thead><tbody>"
        + "".join(circ_rows)
        + "</tbody></table>"
    )

    stat_rows = []
    for i, mod in enumerate(MODULES):
        fo = raw_fanout[i]
        fi = fan_in[i]
        inst = f"{fo / (fi + fo):.2f}" if (fi + fo) > 0 else "0.00"
        dc = fi * fo
        flag = (
            "KRITIEK"
            if fo >= 500 or fi >= 500
            else "HOOG"
            if fo >= 200 or fi >= 200
            else "MEDIUM"
            if fo >= 80 or fi >= 80
            else "LAAG"
            if fo >= 20 or fi >= 20
            else "OK"
        )
        fcls = "sev-k" if flag == "KRITIEK" else "sev-m" if flag in ("HOOG", "MEDIUM") else "sev-l"
        stat_rows.append(
            f"<tr><td>{mod}</td><td>{file_counts[i]}</td><td>{fo}</td><td>{fi}</td>"
            f"<td>{inst}</td><td>{dc}</td><td class='{fcls}'>{flag}</td></tr>"
        )
    stats_tab = (
        '<table class="vtable"><thead><tr><th>Module</th><th>Files</th>'
        "<th>fan-OUT</th><th>fan-IN</th><th>I</th><th>D_c</th><th>Oordeel</th></tr></thead><tbody>"
        + "".join(stat_rows)
        + "</tbody></table>"
        '<p class="note">I = fan-out/(fan-in+fan-out). D_c = fan-in x fan-out (Henry-Kafura).</p>'
    )

    unc_rows = (
        "".join(f"<tr><td>src.core.{m}</td><td>{c}</td></tr>" for m, c in all_unc.most_common(20))
        if all_unc
        else "<tr><td colspan='2'>Geen ongeclassificeerde imports.</td></tr>"
    )
    unc_tab = (
        '<table class="vtable"><thead><tr><th>Module</th><th>Aantal</th></tr></thead><tbody>'
        + unc_rows
        + "</tbody></table>"
        '<p class="note">Voeg toe aan MODULE_MAP in dsm_full_analysis.py als relevant.</p>'
    )

    html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SanskritiSetu DSM v7</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:monospace;font-size:13px;background:#1a1a2e;color:#e0e0e0}}
header{{background:#16213e;padding:16px 24px;border-bottom:2px solid #0f3460}}
h1{{font-size:20px;color:#00b4d8;margin-bottom:6px}}
.meta{{color:#aaa;font-size:11px;margin-bottom:8px}}
.badges{{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}}
.badge-red{{background:#c0392b;color:#fff;padding:3px 8px;border-radius:3px;font-size:11px}}
.badge-green{{background:#27ae60;color:#fff;padding:3px 8px;border-radius:3px;font-size:11px}}
.badge-grey{{background:#555;color:#fff;padding:3px 8px;border-radius:3px;font-size:11px}}
nav.tabs{{background:#16213e;padding:0 24px;border-bottom:1px solid #0f3460}}
nav.tabs button{{background:none;border:none;color:#aaa;padding:12px 16px;cursor:pointer;font-size:13px}}
nav.tabs button.active{{color:#00b4d8;border-bottom:2px solid #00b4d8}}
.tab{{display:none;padding:20px;overflow-x:auto}}
.tab.active{{display:block}}
h2{{color:#00b4d8;margin:0 0 12px;font-size:16px}}
h3{{color:#aaa;margin:12px 0 8px;font-size:13px}}
p.note{{color:#666;font-size:11px;margin-top:10px}}
table.dsm{{border-collapse:collapse;font-size:11px}}
table.dsm th,table.dsm td{{border:1px solid #333;padding:3px 5px;text-align:right;min-width:32px}}
table.dsm th{{background:#16213e;color:#aaa;text-align:center}}
td.diag{{background:#2a2a2a;color:#555;text-align:center}}
td.zero{{color:#444}}
td.viol{{background:#4d1111;color:#ff6b6b;font-weight:bold}}
td.ok{{background:#112d11;color:#6bff6b}}
td.raw{{color:#888}}
td.fo{{background:#16213e;color:#00b4d8;font-weight:bold}}
td.inst{{background:#16213e;color:#777}}
tr.fi-row td,tr.fi-row th{{background:#16213e;color:#777}}
.vnum{{font-size:12px}}
sup.aok{{font-size:9px;color:#777}}
table.vtable{{border-collapse:collapse;width:100%;max-width:900px}}
table.vtable th,table.vtable td{{border:1px solid #333;padding:5px 10px;text-align:left}}
table.vtable th{{background:#16213e;color:#aaa}}
td.vf{{font-family:monospace;font-size:11px;color:#aaa}}
td.vc{{text-align:right;color:#ff6b6b;font-weight:bold}}
.sev-k{{color:#ff6b6b;font-weight:bold}}
.sev-m{{color:#f39c12}}
.sev-l{{color:#6bff6b}}
</style>
</head>
<body>
<header>
<h1>SanskritiSetu DSM v7 -- Violation-Aware</h1>
<div class="meta">Gegenereerd: {gen_date} | ADR-033, ADR-034 | scripts/dsm_full_analysis.py --html</div>
<div class="badges">
<span class="badge-red">{total_v} echte violations</span>
<span class="badge-grey">ceiling: {v_ceil}</span>
<span class="badge-green">shared fan-out: 0</span>
</div>
</header>
<nav class="tabs">
<button class="active" onclick="show('matrix',this)">DSM Matrix</button>
<button onclick="show('violations',this)">Violations ({total_v})</button>
<button onclick="show('circulaire',this)">Circulaire Deps</button>
<button onclick="show('stats',this)">Statistieken</button>
<button onclick="show('unc',this)">Ongeclassificeerd</button>
</nav>
<div id="matrix" class="tab active"><h2>Violation-Aware DSM Matrix</h2>{matrix_tab}</div>
<div id="violations" class="tab"><h2>ADR-033 Violations ({total_v})</h2>{violations_tab}</div>
<div id="circulaire" class="tab"><h2>Circulaire Dependencies</h2>{circulaire_tab}</div>
<div id="stats" class="tab"><h2>Module Statistieken</h2>{stats_tab}</div>
<div id="unc" class="tab"><h2>Ongeclassificeerde Imports</h2>{unc_tab}</div>
<script>
function show(id,btn){{
document.querySelectorAll('.tab').forEach(function(t){{t.classList.remove('active')}});
document.querySelectorAll('nav.tabs button').forEach(function(b){{b.classList.remove('active')}});
document.getElementById(id).classList.add('active');
btn.classList.add('active');
}}
</script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="DSM Analysis")
    parser.add_argument("--html", metavar="OUTPUT", help="Generate HTML report to OUTPUT")
    args = parser.parse_args()
    if args.html:
        generate_html(args.html)
    else:
        main()
