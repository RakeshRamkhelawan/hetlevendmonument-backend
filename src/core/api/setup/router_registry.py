# dsm:exempt reason: bootstrap -- router-registratie draait eenmalig bij startup
# (phase3_available, phase4_available). Registreert 20+ actieve routers die nog niet naar
# registries/ zijn gemigreerd. TODO(SP-VOLGENDE): migreer resterende routers naar registries/
# en reduceer dit bestand tot een shim.
import logging
import os

from fastapi import FastAPI


logger = logging.getLogger(__name__)

# --- Optional Imports (Flags) ---
# NOTE: the 11 non-optional router imports that were here (regels 13-29) are now
# lazy-loaded inside register_routers() per ADR-033 / Stap 0A.
# They moved to avoid ~78 transitieve imports at pytest-collectie time.

# Phase 2
try:
    from src.core.api.phase2_endpoints import phase2_router  # type: ignore[attr-defined]
except ImportError as e:
    logger.warning(f"Phase 2 endpoints not available: {e}")
    phase2_router = None  # NOTE: optional router, None when module import fails

# Goal (Phase 3+)
try:
    from src.core.api.goal_endpoints import router as goal_router  # type: ignore[attr-defined]

    goal_endpoints_available = True
except ImportError as e:
    logger.warning(f"Goal endpoints not available: {e}")
    goal_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    goal_endpoints_available = False

# Collaboration (Phase 3)
try:
    from src.core.api.collaboration_endpoints import router as collaboration_router

    phase3_available = True
except ImportError as e:
    logger.warning(f"Phase 3 collaboration endpoints not available: {e}")
    collaboration_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    phase3_available = False

# Workflow (Phase 2)
try:
    from src.core.api.workflow_endpoints import router as workflow_router  # type: ignore[attr-defined]
except ImportError as e:
    logger.warning(f"Workflow endpoints not available: {e}")
    workflow_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails

# Workflow Suggestions
try:
    from src.core.api.workflow_suggestions_endpoints import router as workflow_suggestions_router

    workflow_suggestions_available = True
except ImportError as e:
    logger.warning(f"Workflow suggestions endpoints not available: {e}")
    workflow_suggestions_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    workflow_suggestions_available = False

# Workflow Builder
try:
    from src.core.api.workflow_builder_endpoints import router as workflow_builder_router

    workflow_builder_available = True
except ImportError as e:
    logger.warning(f"Workflow builder endpoints not available: {e}")
    workflow_builder_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    workflow_builder_available = False

# Agentic Workflow (Phase 7.1)
# MIGRATED: registered via registries/agentic.py (SP-API-009 Dag 1)
# try:
#     from src.core.api.agentic_flow_endpoints import router as agentic_flow_router
#     agentic_flow_available = True
# except ImportError as e:
#     pass
agentic_flow_router = None  # NOTE: MIGRATED to registries/agentic.py
agentic_flow_available = False

# Pack Feedback & Global Repository
try:
    from src.core.api.pack_feedback_endpoints import router as pack_feedback_router

    pack_feedback_available = True
except ImportError as e:
    logger.warning(f"Pack feedback endpoints not available: {e}")
    pack_feedback_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    pack_feedback_available = False

# Mission Lifecycle
try:
    from src.core.api.mission_endpoints import router as mission_router  # type: ignore[attr-defined]

    mission_endpoints_available = True
except ImportError as e:
    logger.warning(f"Mission endpoints not available: {e}")
    mission_router = None  # NOTE: optional router, None when module import fails
    mission_endpoints_available = False

# Synthesis
try:
    from src.core.api.synthesis_endpoints import router as synthesis_router  # type: ignore[attr-defined]

    synthesis_endpoints_available = True
except ImportError as e:
    logger.warning(f"Synthesis endpoints not available: {e}")
    synthesis_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    synthesis_endpoints_available = False

# Governance
try:
    from src.core.api.governance_endpoints import router as governance_router  # type: ignore[attr-defined]

    governance_endpoints_available = True
except ImportError as e:
    logger.warning(f"Governance endpoints not available: {e}")
    governance_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    governance_endpoints_available = False

# Audit
try:
    from src.core.api.audit_endpoints import router as audit_router

    audit_endpoints_available = True
except ImportError as e:
    logger.warning(f"Audit endpoints not available: {e}")
    audit_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    audit_endpoints_available = False

# Analytics
# MIGRATED: registered via registries/core_api.py (SP-API-009 Dag 1)
# try:
#     from src.core.api.analytics_endpoints import router as analytics_router
#     analytics_available = True
# except ImportError as e:
#     pass
analytics_router = None  # NOTE: MIGRATED to registries/core_api.py
analytics_available = False

# Subagent (Phase 1) -- migrated to v1/subagents/ (SP-API-007 Dag 3); registered via registries/agents.py
# from src.core.api.subagent_endpoints import subagent_router
subagent_router = None  # NOTE: migrated shim, kept for backwards compat check
subagent_available = False

# Autonomous (Phase 4)
try:
    from src.core.api.autonomous_endpoints import router as autonomous_router

    phase4_available = True
except ImportError as e:
    logger.warning(f"Phase 4 autonomous endpoints not available: {e}")
    autonomous_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    phase4_available = False

# Security
try:
    from src.core.api.security_endpoints import router as security_router  # type: ignore[attr-defined]

    security_available = True
except ImportError as e:
    logger.warning(f"Security endpoints not available: {e}")
    security_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    security_available = False

# Metrics Middleware
try:
    from src.core.middleware.metrics_middleware import (
        ToolBrokerMetricsMiddleware,
        generate_metrics_response,
    )

    metrics_middleware_available = True
except ImportError as e:
    logger.warning(f"Metrics middleware not available: {e}")
    metrics_middleware_available = False

# Prediction (Phase 5) -- migrated to registries/analytics.py (SP-API-007)
prediction_router = None  # NOTE: migrated to v1/prediction/
phase5_available = False

# NLP
try:
    from src.core.api.nlp_endpoints import router as nlp_router

    nlp_available = True
except ImportError as e:
    logger.warning(f"Enhanced NLP endpoints not available: {e}")
    nlp_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    nlp_available = False

# Production Integration
try:
    from src.core.api.production_endpoints import router as production_router

    production_available = True
except ImportError as e:
    logger.warning(f"Production integration endpoints not available: {e}")
    production_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    production_available = False

# Learning
try:
    from src.core.api.learning_endpoints import router as learning_router

    learning_available = True
    logger.info("Learning endpoints (Autonomous Workflow Training) loaded")
except ImportError as e:
    logger.warning(f"Learning endpoints not available: {e}")
    learning_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    learning_available = False

# Models
try:
    from src.core.api.models_endpoints import router as models_router  # type: ignore[attr-defined]

    models_available = True
    logger.info("Model Registry endpoints (MLflow Lifecycle Management) loaded")
except ImportError as e:
    logger.warning(f"Model Registry endpoints not available: {e}")
    models_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    models_available = False

# Experimentation -- migrated to registries/analytics.py (SP-API-007)
# experimentation_endpoints.py replaced by src/core/api/v1/experimentation/ (SP-API-007 Dag 1)
experimentation_router = None  # NOTE: migrated, kept for reference
experimentation_available = False

# Monitoring Dashboard (Enhanced)
# TODO(SP-VOLGENDE): monitoring_dashboard_endpoints dubbel geregistreerd (setup=no-prefix, optional.py=/api prefix)
# Prefix-discrepantie: setup registreert zonder prefix, registries/optional.py met prefix="/api".
# Niet verwijderd totdat de prefix-impact is onderzocht en client-side URLs zijn bijgewerkt.
try:
    from src.core.api.monitoring_dashboard_endpoints import router as monitoring_router

    monitoring_available = True
    logger.info("Enhanced monitoring dashboard endpoints loaded")
except ImportError as e:
    logger.warning(f"Enhanced monitoring dashboard not available: {e}")
    # Fallback to legacy
    try:
        from src.core.api.monitoring_endpoints import router as monitoring_router  # type: ignore[attr-defined]

        monitoring_available = True
        logger.info("Legacy monitoring endpoints loaded as fallback")
    except ImportError as fallback_e:
        logger.warning(f"No monitoring endpoints available: {fallback_e}")
        monitoring_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
        monitoring_available = False

# Performance Analytics (P4.2)
try:
    from src.core.api.performance_analytics_endpoints import router as performance_analytics_router

    performance_analytics_available = True
    logger.info("P4.2 Performance Analytics router imported successfully")
except ImportError as e:
    logger.warning(f"P4.2 Performance Analytics endpoints not available: {e}")
    performance_analytics_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    performance_analytics_available = False

# AI Features (Phase 2.4) -- migrated to v1/ai_features/ (SP-API-007 Dag 2)
# Registration now handled by registries/analytics.py via domain_router.
# Legacy import kept as comment for traceability.
# from src.core.api.ai_features_endpoints import router as ai_features_router
ai_features_router = None  # NOTE: replaced by v1/ai_features/ domain_router
ai_features_available = False

# Company Layer (Paperclip Integration - Phase 8/9)
# MIGRATED: all company routers registered via registries/company.py (SP-API-009 Dag 1)
# try:
#     from src.core.api.v1.company.board_router import router as board_router
#     from src.core.api.v1.company.department_router import router as department_router
#     from src.core.api.v1.company.external_agent_router import router as external_agent_router
#     from src.core.api.v1.company.goal_router import router as goal_router
#     from src.core.api.v1.company.onboarding_router import router as onboarding_router
#     from src.core.api.v1.company.router import router as company_router
#     from src.core.api.v1.company.template_router import router as template_router
#     company_available = True
# except ImportError as e:
#     pass
company_router = None  # NOTE: MIGRATED to registries/company.py
department_router = None
# goal_router intentionally NOT set to None here -- Phase 3 goal_endpoints import above takes precedence
board_router = None
external_agent_router = None
template_router = None
onboarding_router = None
company_available = False

# Knowledge (Phase 3)
try:
    from src.core.api.knowledge_endpoints import router as knowledge_router

    knowledge_available = True
except ImportError as e:
    logger.warning(f"Knowledge endpoints not available: {e}")
    knowledge_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    knowledge_available = False

# CVA Autonomous
try:
    from src.core.api.cva_autonomous_endpoints import cva_autonomous_router  # type: ignore[attr-defined]

    cva_autonomous_available = True
except Exception as e:
    logger.error(f"Failed to import CVA autonomous endpoints: {e}")
    cva_autonomous_router = None  # NOTE: optional router, None when module import fails
    cva_autonomous_available = False

# Events (Event System Status & Debugging)
# MIGRATED: registered via registries/analytics.py (SP-API-009 Dag 1)
# try:
#     from src.core.api.events_endpoints import router as events_router
#     events_available = True
# except ImportError as e:
#     pass
events_router = None  # NOTE: MIGRATED to registries/analytics.py
events_available = False

# Routing (GunaRouter - Semantic + Deterministic)
try:
    from src.core.api.v1.routing.router import router as routing_router

    routing_available = True
    logger.info("GunaRouter endpoints loaded")
except ImportError as e:
    logger.warning(f"Routing endpoints not available: {e}")
    routing_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    routing_available = False

# Sync (YJS Document Synchronization)
try:
    from src.core.api.v1.sync.router import router as sync_router

    sync_available = True
    logger.info("YJS Sync endpoints loaded")
except ImportError as e:
    logger.warning(f"Sync endpoints not available: {e}")
    sync_router = None  # type: ignore[assignment]  # NOTE: optional router, None when module import fails
    sync_available = False

# Feature Flags (Late Import Handling)
# GDPR (Late Import Handling)
# LLM (Late Import Handling)


def register_routers(app: FastAPI) -> None:
    """
    Registers all routers with the FastAPI application.
    Encapsulates all inclusion logic and conditional checks.

    SP-API-009 Dag 1 categorisatie (2026-06-06):
    - Categorie A (DUBBEL -> uitgecommentarieerd): agentic_flow, analytics, events,
      company/*, monitoring_dashboard(TODO-prefix), sandbox(TODO-prefix)
    - Categorie B (UNIEK shim -> TODO verplaatsen naar registries/):
      ai_features, feature_flags, governance, models, monitoring, security,
      sentiment_scanner, subagent, synthesis, workflow, v1.routing, v1.sync
    - Categorie C (UNIEK, geen v1/ -> bewaren met TODO):
      admin, audit, autonomous, chat, collaboration, cva_autonomous, debug,
      goal, knowledge, learning, management, mission, nlp, pack_feedback,
      performance_analytics, phase2, production, system, task, websocket,
      workflow_builder, workflow_suggestions
    TODO(SP-VOLGENDE): verplaats alle Categorie B naar juiste registries/ files
    TODO(SP-VOLGENDE): migreer Categorie C flat files naar v1/ dan naar registries/
    """
    # Lazy imports (moved from module-level per ADR-033 Stap 0A)
    from src.core.api import orchestrator_endpoints
    from src.core.api.admin_endpoints import router as admin_router  # type: ignore[attr-defined]
    from src.core.api.chat_endpoints import router as chat_router
    from src.core.api.debug_endpoints import router as debug_router
    from src.core.api.learning_endpoints import router as learning_router
    from src.core.api.management_endpoints import router as management_router
    from src.core.api.sandbox_endpoints import (
        router as sandbox_router,
    )  # TODO(SP-VOLGENDE): dubbel (integrations.py=/api/v1, setup=no-prefix); prefix-discrepantie onderzoeken
    from src.core.api.sentiment_scanner_endpoints import router as sentiment_router  # type: ignore[attr-defined]
    from src.core.api.system_endpoints import router as system_router
    from src.core.api.task_endpoints import router as task_router
    from src.core.api.websocket_endpoints import router as websocket_router

    logger.info("Starting router registration...")

    # Monitoring
    if monitoring_router and monitoring_available:
        app.include_router(monitoring_router)
        logger.info("Monitoring endpoints registered successfully")

    # Performance Analytics
    if performance_analytics_router and performance_analytics_available:
        app.include_router(performance_analytics_router, prefix="/api/v1/performance")
        logger.info("P4.2 Performance Analytics endpoints registered successfully")

    # AI Features
    if ai_features_router and ai_features_available:
        app.include_router(ai_features_router, prefix="/api/v1/ai")
        logger.info("Fase 2.4 AI Features endpoints registered successfully")

    # Company Layer (Paperclip Integration)
    if company_router and company_available:
        try:
            app.include_router(company_router, prefix="/api/v1")
            if department_router:
                app.include_router(department_router, prefix="/api/v1")
            if goal_router:
                app.include_router(goal_router, prefix="/api/v1")
            if board_router:
                app.include_router(board_router, prefix="/api/v1")
            if external_agent_router:
                app.include_router(external_agent_router, prefix="/api/v1")
            if template_router:
                app.include_router(template_router, prefix="/api/v1")
            if onboarding_router:
                app.include_router(onboarding_router, prefix="/api/v1")
            logger.info(
                "FASE 8/9 Company Layer endpoints (Paperclip Integration) registered successfully"
            )
        except Exception as e:
            logger.error(f"Failed to register Company Layer endpoints: {e}")
    else:
        logger.warning("Company Layer router NOT included - Paperclip features unavailable")

    # Auth & Admin & Management
    app.include_router(admin_router)
    app.include_router(management_router)

    # Knowledge
    if knowledge_router and knowledge_available:
        app.include_router(knowledge_router, prefix="/api/v1")
        logger.info("FASE 3 Knowledge endpoints registered successfully")

    # Sentiment
    try:
        app.include_router(sentiment_router)
        logger.info("CVA Sentiment Scanner endpoints registered successfully")
    except Exception as e:
        logger.error(f"Failed to register sentiment scanner endpoints: {e}")

    # CVA Autonomous
    if cva_autonomous_router and cva_autonomous_available:
        try:
            app.include_router(cva_autonomous_router)
            logger.info("CVA Autonomous Trigger endpoints registered successfully")
        except Exception as e:
            logger.error(f"Failed to register CVA autonomous endpoints: {e}")

    # Events (Event System Status & Debugging)
    if events_router and events_available:
        try:
            app.include_router(events_router, prefix="/api/v1")
            logger.info("Event system endpoints registered successfully")
        except Exception as e:
            logger.error(f"Failed to register event endpoints: {e}")

    # Routing (GunaRouter - Semantic + Deterministic)
    if routing_router and routing_available:
        try:
            app.include_router(routing_router, prefix="/api/v1")
            logger.info("GunaRouter endpoints registered successfully")
        except Exception as e:
            logger.error(f"Failed to register routing endpoints: {e}")

    # Sync (YJS Document Synchronization)
    if sync_router and sync_available:
        try:
            app.include_router(sync_router, prefix="/api/v1")
            logger.info("YJS Sync endpoints registered successfully")
        except Exception as e:
            logger.error(f"Failed to register sync endpoints: {e}")

    # Subagent
    if subagent_router and subagent_available:
        app.include_router(subagent_router)
        logger.info("Subagent endpoints registered successfully")

    # Phase 2 -- gated by PHASE2_ENABLED feature flag (default: false)
    if phase2_router and os.getenv("PHASE2_ENABLED", "false").lower() == "true":
        app.include_router(phase2_router)

    # Goal
    if goal_endpoints_available and goal_router:
        app.include_router(goal_router, prefix="/api/v1")
        logger.info("FASE 3+ Goal endpoints (autonomous execution) enabled")

    # Collaboration (Phase 3)
    if collaboration_router and phase3_available:
        app.include_router(collaboration_router)
        logger.info("Phase 3 endpoints registered successfully")

    # Autonomous (Phase 4)
    if autonomous_router and phase4_available:
        app.include_router(autonomous_router)
        logger.info("Phase 4 endpoints registered successfully")

    # Security
    if security_router and security_available:
        app.include_router(security_router)
        logger.info("Security endpoints registered successfully")
    else:
        logger.warning(f"Security router NOT included - available: {security_available}")

    # Workflow
    if workflow_router:
        app.include_router(workflow_router)
        logger.info("Workflow endpoints registered successfully")
    else:
        logger.error("Phase 2 router is None - not registered")

    # Workflow Suggestions
    if workflow_suggestions_router and workflow_suggestions_available:
        app.include_router(workflow_suggestions_router)
        logger.info("Workflow Suggestions endpoints registered successfully")
    else:
        logger.warning("Workflow Suggestions router NOT included")

    # Workflow Builder
    if workflow_builder_router and workflow_builder_available:
        app.include_router(workflow_builder_router)
        logger.info("Workflow Builder endpoints registered successfully")
    else:
        logger.warning("Workflow Builder router NOT included")

    # Agentic Workflow (Phase 7.1)
    if agentic_flow_router and agentic_flow_available:
        app.include_router(agentic_flow_router)
        logger.info("Agentic Flow endpoints registered successfully")
    else:
        logger.warning("Agentic Flow router NOT included")

    # Pack Feedback & Global Repository
    if pack_feedback_available and pack_feedback_router:
        app.include_router(pack_feedback_router)
        logger.info("Pack Feedback endpoints registered successfully")
    else:
        logger.warning("Pack Feedback router NOT included")

    # Mission Lifecycle
    if mission_router and mission_endpoints_available:
        app.include_router(mission_router)
        logger.info("Mission Lifecycle endpoints registered successfully")
    else:
        logger.warning("Mission Lifecycle router NOT included")

    # Synthesis
    if synthesis_router and synthesis_endpoints_available:
        app.include_router(synthesis_router)
        logger.info("Synthesis endpoints registered successfully")
    else:
        logger.warning("Synthesis router NOT included")

    # Governance
    if governance_router and governance_endpoints_available:
        app.include_router(governance_router)
        logger.info("Governance endpoints registered successfully")
    else:
        logger.warning("Governance router NOT included")

    # Audit
    if audit_router and audit_endpoints_available:
        app.include_router(audit_router)
        logger.info("Audit endpoints registered successfully")
    else:
        logger.warning("Audit router NOT included")

    # Analytics
    if analytics_router and analytics_available:
        app.include_router(analytics_router)
        logger.info("Analytics endpoints registered successfully")
    else:
        logger.warning("Analytics router NOT included")

    # Prediction (Phase 5)
    if prediction_router and phase5_available:
        app.include_router(prediction_router)
        logger.info("Phase 5 prediction endpoints registered successfully")
    else:
        logger.warning("Phase 5 prediction router NOT included - available: %s", phase5_available)

    # NLP
    if nlp_router and nlp_available:
        app.include_router(nlp_router)
        logger.info("Enhanced NLP endpoints registered successfully")
    else:
        logger.warning(f"Enhanced NLP router NOT included - available: {nlp_available}")

    # Production
    if production_router and production_available:
        app.include_router(production_router)
        logger.info("Production integration endpoints registered successfully")
    else:
        logger.warning(
            f"Production integration router NOT included - available: {production_available}"
        )

    # Learning
    if learning_router and learning_available:
        app.include_router(learning_router)
        logger.info("Learning endpoints (Autonomous Workflow Training) registered successfully")
    else:
        logger.warning(f"Learning router NOT included - available: {learning_available}")

    # Models
    if models_router and models_available:
        app.include_router(models_router)
        logger.info(
            "Model Registry endpoints (MLflow Lifecycle Management) registered successfully"
        )
    else:
        logger.warning(f"Model Registry router NOT included - available: {models_available}")

    # Experimentation
    if experimentation_router and experimentation_available:
        app.include_router(experimentation_router)
        logger.info("Experimentation endpoints (A/B Testing Framework) registered successfully")
    else:
        logger.warning(
            f"Experimentation router NOT included - available: {experimentation_available}"
        )

    # Orchestrator
    app.include_router(orchestrator_endpoints.router)
    logger.info("Orchestrator endpoints registered successfully")

    # System & Refactored Endpoints
    app.include_router(system_router)
    app.include_router(chat_router)
    app.include_router(task_router)
    app.include_router(sandbox_router)
    if learning_router:
        app.include_router(learning_router)

    if os.getenv("APP_DEBUG", "false").lower() == "true":
        app.include_router(debug_router)
        logger.warning("Debug router registered -- APP_DEBUG=true, disable in production")
    else:
        logger.info("Debug router NOT registered (APP_DEBUG not set)")
    app.include_router(websocket_router)
    logger.info(
        "System, Chat, Task, Sandbox, Learning, Debug and WebSocket routers registered successfully"
    )

    # --- Late Imports (Defined inside register_routers to match main.py flow) ---

    # LLM
    try:
        from src.core.llm.llm_endpoints import router as llm_router

        app.include_router(llm_router)
        logger.info("LLM endpoints registered successfully")
    except ImportError as e:
        logger.error(f"CRITICAL: Failed to import LLM router: {e}")

    # Feature Flags
    try:
        from src.core.api.feature_flags_endpoints import router as feature_flags_router  # type: ignore[attr-defined]

        app.include_router(feature_flags_router)
        logger.info("Feature Flags endpoints registered successfully")
    except ImportError as e:
        logger.warning(f"Feature Flags endpoints not available: {e}")

    # GDPR -- migrated to registries/compliance.py (SP-API-005 Dag 1, ADR-033)

    logger.info("Router registration complete.")
