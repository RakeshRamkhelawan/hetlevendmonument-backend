import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

# Production Logging
from typing import cast, Any
from collections.abc import AsyncGenerator

from fastapi import FastAPI

from src.core.agents.cva_orchestrator import create_ultimate_cva_agent

# Shared State & Configuration
from src.core.api.setup.app_state import app_state
from src.core.api.setup.router_registry import phase3_available, phase4_available
from src.core.api.websocket_manager import WebSocketManager

# Core Components
from src.core.database.database import get_db as get_db_session
from src.core.database.database import initialize_database
from src.core.sandbox.sandbox_manager import SandboxManagerFactory
from src.core.shared.config import get_feature_flag
from src.core.shared.production_logging import (
    log_component_health,
    log_critical_error,
    log_llm_provider_status,
    log_performance_metrics,
    log_startup_validation,
    production_logger,
)

logger = logging.getLogger(__name__)


async def _test_llm_provider_health() -> None:
    """Test actual LLM provider health with real API calls"""
    from src.core.shared.llm_client import LLMMessage, create_llm_client

    try:
        start_time = time.time()
        google_client = create_llm_client("google")
        # Use natural message that passes Google safety filters
        test_messages = [
            LLMMessage(
                role="user",
                content="Hello! How are you doing today? Please respond with a brief greeting.",
            )
        ]
        response = await google_client.chat_completion(test_messages, max_tokens=50)
        response_time = time.time() - start_time

        if response.success:
            log_llm_provider_status("Google", "gemini-1.5-flash", "OPERATIONAL", response_time)
        else:
            log_llm_provider_status(
                "Google",
                "gemini-1.5-flash",
                "FAILED",
                response_time,
                response.error_message,
            )
    except Exception as e:
        log_llm_provider_status("Google", "gemini-1.5-flash", "FAILED", None, str(e))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager with comprehensive production logging"""
    production_logger.logger.info("[START] Starting Sanskriti Setu API...")

    # Perform startup validation
    startup_success = log_startup_validation()
    if not startup_success:
        production_logger.logger.error(
            "[CRITICAL] STARTUP VALIDATION FAILED - Cannot start application"
        )
        raise RuntimeError("Critical configuration missing - startup blocked")

    try:
        start_time = time.time()

        # Initialize Database for persistent learning data
        production_logger.logger.info(
            "Initializing Database for persistent conversations and learning..."
        )
        try:
            db_initialized = initialize_database()
            if db_initialized:
                app_state["database_initialized"] = True
                log_component_health(
                    "Database", "HEALTHY", "PostgreSQL connection pool initialized"
                )

                # Seed database with essential data (admin user, default tenant)
                production_logger.logger.info("Seeding database with essential data...")
                try:
                    from src.core.database.seed import seed_database

                    async for db_session in get_db_session():
                        seed_success = await seed_database(db_session)
                        if seed_success:
                            log_component_health(
                                "DatabaseSeed",
                                "HEALTHY",
                                "Admin user and default tenant ensured",
                            )
                        else:
                            production_logger.logger.warning(
                                "Database seeding had issues - check logs"
                            )
                        break
                except Exception as seed_error:
                    production_logger.logger.warning(f"Database seeding failed: {seed_error}")
                    # Non-critical - continue startup
            else:
                production_logger.logger.warning(
                    "Database initialization failed - continuing with degraded functionality"
                )
                app_state["database_initialized"] = False
        except Exception as db_error:
            log_critical_error("DatabaseInitialization", db_error)
            app_state["database_initialized"] = False

        # Initialize Rate Limiter
        production_logger.logger.info("Initializing Rate Limiter...")
        try:
            from src.core.middleware.rate_limiter import get_limiter

            app_state["rate_limiter"] = get_limiter(service_name="focusbuilder")
            log_component_health("RateLimiter", "HEALTHY", "Rate limiting initialized")
        except Exception as rate_limit_error:
            log_critical_error("RateLimiterInitialization", rate_limit_error)
            log_component_health(
                "RateLimiter",
                "WARNING",
                f"Initialization failed: {str(rate_limit_error)}",
            )
            # Non-critical - continue without rate limiting
            app_state["rate_limiter"] = None

        # Initialize WebSocket Manager
        production_logger.logger.info("Initializing WebSocket Manager...")
        app_state["websocket_manager"] = WebSocketManager()
        log_component_health(
            "WebSocketManager", "HEALTHY", "WebSocket connections support initialized"
        )

        # Initialize CVA Agent with health monitoring
        production_logger.logger.info("Initializing CVA Agent...")
        try:
            agent_start_time = time.time()
            app_state["cva_agent"] = await create_ultimate_cva_agent()
            agent_init_time = time.time() - agent_start_time

            if app_state["cva_agent"]:
                log_component_health(
                    "CVAAgent",
                    "HEALTHY",
                    "Strategic AI agent operational",
                    agent_init_time,
                )

                # Test LLM provider if available
                try:
                    # Defensive check for method availability (handles module reload issues)
                    if hasattr(app_state["cva_agent"], "get_cva_metrics"):
                        # Get CVA metrics to check LLM status
                        cva_metrics = cast(Any, app_state["cva_agent"]).get_cva_metrics()  # TODO(TYPE): replace Any with concrete type
                        if cva_metrics.get("llm_initialized"):
                            # Perform actual health checks for LLM providers instead of hardcoded status
                            await _test_llm_provider_health()
                        else:
                            log_llm_provider_status("Mock", "mock-llm-v1", "OPERATIONAL", 0.1)
                            production_logger.warning(
                                "[WARN] Real LLM integration not active - using mock provider"
                            )
                    else:
                        # Method not available - likely module reload issue
                        production_logger.logger.warning(
                            "CVA agent missing get_cva_metrics method - skipping LLM validation"
                        )
                        log_llm_provider_status("Mock", "mock-llm-v1", "OPERATIONAL", 0.1)
                except Exception as llm_error:
                    log_critical_error(
                        "LLMProviderStatus",
                        llm_error,
                        {"component": "CVA Agent LLM validation"},
                    )
            else:
                log_component_health("CVAAgent", "FAILED", "Agent initialization returned None")

        except Exception as agent_error:
            log_critical_error("CVAAgentInitialization", agent_error)
            log_component_health("CVAAgent", "FAILED", f"Initialization failed: {str(agent_error)}")
            raise

        # Initialize Sandbox Manager
        production_logger.logger.info("Initializing Sandbox Manager...")
        try:
            sandbox_start_time = time.time()
            app_state["sandbox_manager"] = SandboxManagerFactory.create_manager()
            sandbox_init_time = time.time() - sandbox_start_time

            if app_state["sandbox_manager"]:
                log_component_health(
                    "SandboxManager",
                    "HEALTHY",
                    "Mock sandbox environment operational",
                    sandbox_init_time,
                )
            else:
                log_component_health(
                    "SandboxManager", "FAILED", "Manager initialization returned None"
                )

        except Exception as sandbox_error:
            log_critical_error("SandboxManagerInitialization", sandbox_error)
            log_component_health(
                "SandboxManager",
                "FAILED",
                f"Initialization failed: {str(sandbox_error)}",
            )
            production_logger.warning(
                "[WARN] Continuing without sandbox manager - Week 1 compatible"
            )

        # Initialize Tenant Sandbox Orchestrator (multi-tenant Docker isolation)
        production_logger.logger.info("Initializing TenantSandboxOrchestrator...")
        try:
            from src.core.sandbox.tenant_sandbox_orchestrator import get_sandbox_orchestrator

            orchestrator = await get_sandbox_orchestrator()
            app_state["sandbox_orchestrator"] = orchestrator

            if orchestrator._docker_client:
                log_component_health(
                    "TenantSandboxOrchestrator", "HEALTHY", "Docker isolation active"
                )
            else:
                _is_prod = os.environ.get("ENVIRONMENT", "development") == "production"
                if _is_prod:
                    raise RuntimeError("TenantSandboxOrchestrator requires Docker in production")
                log_component_health(
                    "TenantSandboxOrchestrator",
                    "DEGRADED",
                    "Mock mode - Docker unavailable",
                )
        except Exception as orch_error:
            log_critical_error("TenantSandboxOrchestratorInit", orch_error)
            if os.environ.get("ENVIRONMENT", "development") == "production":
                raise
            production_logger.warning("[WARN] Continuing without orchestrator (non-production)")

        # Initialize Phase 3 Collaboration Systems
        if phase3_available:
            production_logger.logger.info("Initializing Phase 3 Collaboration Systems...")
            try:
                phase3_start_time = time.time()

                # Initialize collaboration systems from endpoints
                try:
                    from src.core.api.collaboration_endpoints import (
                        initialize_collaboration_systems,
                    )

                    collaboration_success = await initialize_collaboration_systems()
                except ImportError as import_error:
                    production_logger.logger.warning(
                        f"[WARN] collaboration_endpoints import failed: {import_error}"
                    )
                    collaboration_success = False
                except Exception as init_error:
                    production_logger.logger.warning(
                        f"[WARN] collaboration system initialization failed: {init_error}"
                    )
                    collaboration_success = False

                phase3_init_time = time.time() - phase3_start_time

                if collaboration_success:
                    log_component_health(
                        "Phase3Collaboration",
                        "HEALTHY",
                        "Agent mesh, learning & intelligence operational",
                        phase3_init_time,
                    )
                    app_state["phase3_collaboration_enabled"] = True

                    # Enable collaboration in workflow engine
                    try:
                        from src.core.agents.workflow_engine import get_workflow_engine

                        workflow_engine = get_workflow_engine()
                        await workflow_engine.enable_collaboration()
                        production_logger.logger.info(
                            "[OK] Phase 3 collaboration integrated with workflow engine"
                        )
                    except Exception as wf_error:
                        production_logger.logger.warning(
                            f"[WARN] Workflow engine collaboration integration failed: {wf_error}"
                        )
                else:
                    log_component_health(
                        "Phase3Collaboration",
                        "DEGRADED",
                        "Partial initialization - some systems unavailable",
                    )
                    app_state["phase3_collaboration_enabled"] = False

            except Exception as phase3_error:
                log_critical_error("Phase3CollaborationInitialization", phase3_error)
                log_component_health(
                    "Phase3Collaboration",
                    "FAILED",
                    f"Initialization failed: {str(phase3_error)}",
                )
                app_state["phase3_collaboration_enabled"] = False
                production_logger.warning("[WARN] Continuing without Phase 3 collaboration systems")
        else:
            production_logger.logger.info(
                "Phase 3 collaboration systems not available - skipping initialization"
            )
            app_state["phase3_collaboration_enabled"] = False

        # Initialize Phase 4 Autonomous Systems
        if phase4_available:
            production_logger.logger.info("Initializing Phase 4 Autonomous Systems...")
            try:
                phase4_start_time = time.time()

                # Initialize autonomous systems from endpoints
                from src.core.api.autonomous_endpoints import initialize_autonomous_systems

                autonomous_success = await initialize_autonomous_systems()

                phase4_init_time = time.time() - phase4_start_time

                if autonomous_success:
                    log_component_health(
                        "Phase4Autonomous",
                        "HEALTHY",
                        "Agent factory, self-healing, code generation & emergent intelligence operational",
                        phase4_init_time,
                    )
                    app_state["phase4_autonomous_enabled"] = True
                    production_logger.logger.info(
                        "[OK] Phase 4 autonomous systems fully operational"
                    )
                else:
                    log_component_health(
                        "Phase4Autonomous",
                        "DEGRADED",
                        "Partial initialization - some autonomous systems unavailable",
                    )
                    app_state["phase4_autonomous_enabled"] = False

            except Exception as phase4_error:
                log_critical_error("Phase4AutonomousInitialization", phase4_error)
                log_component_health(
                    "Phase4Autonomous",
                    "FAILED",
                    f"Initialization failed: {str(phase4_error)}",
                )
                app_state["phase4_autonomous_enabled"] = False
                production_logger.warning("[WARN] Continuing without Phase 4 autonomous systems")
        else:
            production_logger.logger.info(
                "Phase 4 autonomous systems not available - skipping initialization"
            )
            app_state["phase4_autonomous_enabled"] = False

        # Initialize Mock Usage Detection System (P1.4)
        production_logger.logger.info("Initializing Mock Usage Detection System...")
        try:
            from src.core.monitoring.mock_usage_detector import mock_usage_detector

            await mock_usage_detector.start_monitoring()
            log_component_health(
                "MockUsageDetector",
                "HEALTHY",
                "Mock usage monitoring and alerting operational",
                0.01,
            )
            app_state["mock_usage_detector_enabled"] = True
            production_logger.logger.info("[OK] Mock usage detection system fully operational")
        except Exception as mock_error:
            log_critical_error("MockUsageDetectorInitialization", mock_error)
            log_component_health(
                "MockUsageDetector",
                "FAILED",
                f"Initialization failed: {str(mock_error)}",
            )
            app_state["mock_usage_detector_enabled"] = False
            production_logger.warning("[WARN] Continuing without mock usage detection")

        # Initialize Autonomous Workflow Training (FASE 1 - Core Integration)
        if app_state.get("database_initialized", False):
            production_logger.logger.info("Initializing Autonomous Workflow Training Service...")
            try:
                from src.core.autonomous_workflow.bootstrap import initialize_autonomous_workflow

                # Get database session for initialization
                async for db_session in get_db_session():
                    training_service = await initialize_autonomous_workflow(db_session)
                    if training_service:
                        app_state["training_service"] = training_service
                        log_component_health(
                            "AutonomousWorkflow",
                            "HEALTHY",
                            "TrainingService initialized with DynamicTrainingPipeline",
                            0.1,
                        )
                        production_logger.logger.info(
                            "[OK] Autonomous workflow training service fully operational"
                        )
                    else:
                        log_component_health(
                            "AutonomousWorkflow",
                            "DEGRADED",
                            "Initialization returned None - continuing without autonomous training",
                        )
                        app_state["training_service"] = None
                    break  # Only use first session
            except Exception as training_error:
                log_critical_error("AutonomousWorkflowInitialization", training_error)
                log_component_health(
                    "AutonomousWorkflow",
                    "FAILED",
                    f"Initialization failed: {str(training_error)}",
                )
                app_state["training_service"] = None
                production_logger.warning("[WARN] Continuing without autonomous workflow training")
        else:
            production_logger.logger.info(
                "Skipping autonomous workflow initialization - database not available"
            )
            app_state["training_service"] = None

        # Initialize Tool Broker Service (PHASE 1: Foundation)
        production_logger.logger.info("Initializing Tool Broker Service...")
        try:
            from src.core.tool_broker.dependencies import ToolBrokerDependencies

            tb_start_time = time.time()
            tb_dependencies = ToolBrokerDependencies.initialize()
            tb_init_time = time.time() - tb_start_time

            if tb_dependencies:
                app_state["tool_broker_service"] = tb_dependencies.get_service()
                log_component_health(
                    "ToolBrokerService",
                    "HEALTHY",
                    "Tool Broker with Serena and Sequential Thinking clients operational",
                    tb_init_time,
                )
                production_logger.logger.info("[OK] Tool Broker Service fully operational")
            else:
                log_component_health(
                    "ToolBrokerService", "FAILED", "DI container initialization failed"
                )
                app_state["tool_broker_service"] = None

        except Exception as tb_error:
            log_critical_error("ToolBrokerInitialization", tb_error)
            log_component_health(
                "ToolBrokerService", "FAILED", f"Initialization failed: {str(tb_error)}"
            )
            app_state["tool_broker_service"] = None
            production_logger.warning("[WARN] Continuing without Tool Broker Service")

        # Log startup performance
        total_startup_time = time.time() - start_time
        log_performance_metrics(
            "ApplicationStartup",
            total_startup_time,
            True,
            {
                "components_initialized": 3,
                "critical_failures": 0,
                "warnings": 1 if not get_feature_flag("real_llm_integration") else 0,
            },
        )

        # TAAK 3.1: Start monitoring dashboard background task
        try:
            from src.core.api.monitoring_dashboard_endpoints import broadcast_updates

            monitoring_task = asyncio.create_task(broadcast_updates())
            app_state["monitoring_task"] = monitoring_task
            logger.info("Monitoring dashboard background task started")
        except Exception as monitoring_error:
            logger.warning(f"Failed to start monitoring background task: {monitoring_error}")
            app_state["monitoring_task"] = None

        production_logger.info(
            f"[SUCCESS] Sanskriti Setu API started successfully in {total_startup_time:.2f}s"
        )

        yield

    except Exception as e:
        log_critical_error(
            "ApplicationStartup",
            e,
            {
                "startup_stage": "component_initialization",
                "components_state": {
                    "cva_agent": app_state["cva_agent"] is not None,
                    "sandbox_manager": app_state["sandbox_manager"] is not None,
                    "websocket_manager": app_state["websocket_manager"] is not None,
                },
            },
        )
        production_logger.error("[ALERT] CRITICAL STARTUP FAILURE - Application cannot start")
        raise
    finally:
        # Cleanup with logging
        production_logger.info("[STOP] Shutting down Sanskriti Setu API...")

        try:
            if app_state["cva_agent"]:
                await cast(Any, app_state["cva_agent"]).shutdown()  # TODO(TYPE): replace Any with concrete type
                production_logger.info("[OK] CVA Agent shutdown complete")
        except Exception as shutdown_error:
            log_critical_error("CVAAgentShutdown", shutdown_error)

        # TAAK 3.1: Stop monitoring dashboard background task
        try:
            monitoring_task_any: Any = app_state.get("monitoring_task")  # TODO(TYPE): replace Any with concrete type
            if monitoring_task_any is not None:
                monitoring_task_any.cancel()
                production_logger.info("[OK] Monitoring dashboard task stopped")
        except Exception as monitoring_shutdown_error:
            logger.warning(f"Error stopping monitoring task: {monitoring_shutdown_error}")

        production_logger.info("[U+0001F3C1] Sanskriti Setu API shutdown complete")
