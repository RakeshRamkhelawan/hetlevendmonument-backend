"""
Unified FastAPI Server - FASE 9 Implementation
Consolidated single-server architecture with agent sub-modules.
Compliant with Single Server Policy from Instructions.md.

This module serves as the clean entry point for the application.
All startup/shutdown logic, middleware, and router registration
are delegated to dedicated modules for maintainability.
"""

# =============================================================================
# CRITICAL: Patch bcrypt/passlib compatibility FIRST
# Must be before any passlib imports
# =============================================================================
from src.core.noodstop import model_deur  # noqa: F401  (opstartpunt: meldt de noodstopcontrole van de modeldeur aan)
from src.core.security.bcrypt_patch import patch_bcrypt_about_attribute

patch_bcrypt_about_attribute()

# Environment configuration
import os

from src.core.env_loader import setup_environment

setup_environment()

from collections.abc import Callable

# =============================================================================
# IMPORTS
# =============================================================================
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_client import generate_latest
from starlette.responses import Response

from src.core.api.setup.middleware_config import setup_middleware

# Modular components
from src.core.app_lifespan import app_lifespan
from src.core.exceptions import register_exception_handlers

ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()


# =============================================================================
# CONFIGURATION VALIDATION (Security requirement)
# =============================================================================
from src.core.config.config_validator import validate_config_at_startup
from src.core.container import get_container
from src.core.logging.loguru_config import configure_logging

if not (os.getenv("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ):
    validate_config_at_startup()
configure_logging()

logger.info("FastAPI application initialized")

# =============================================================================
# APPLICATION FACTORY
# =============================================================================


def wire_container() -> None:
    """Wire dependency injection container (call once at startup)."""
    container = get_container()
    container.wire(
        modules=[
            "src.core.api.dependencies",
            "src.core.api.admin_endpoints",
            "src.core.api.agent_endpoints",
            "src.core.api.ai_features_endpoints",
            "src.core.api.cva_endpoints",
            "src.core.api.document_endpoints",
            "src.core.api.management_endpoints",
            "src.core.api.auth.router",
            "src.core.api.orchestrator_endpoints",
            "src.core.api.rag_endpoints",
            "src.core.api.user_management_endpoints",
            "src.core.api.v1.agentic.router",
            "src.core.api.v1.ai_copilot.router",
            "src.core.api.v1.autonomous.router",
            "src.core.api.v1.collaboration.router",
            "src.core.api.v1.gamification.router",
            "src.core.api.v1.ml.router",
            "src.core.api.v1.privacy.router",
            "src.core.api.v1.system.llm_status",
            "src.core.api.v1.terminal.router",
            "src.core.api.v1.personas.router",
            "src.core.api.assistant_endpoints",
            "src.core.api.copilot_websocket_endpoints",
            "src.core.api.agentic_flow_endpoints",
            "src.domains.agentic.api.experiments",
        ]
    )
    logger.info("Dependency injection container wired")


def create_app(testing: bool = False) -> FastAPI:
    """
    Application factory to create and configure the FastAPI app.
    This allows for isolated app instances during testing.

    Args:
        testing: When True, disables lifespan and production-only init
                 for faster, deterministic test startup.
    """
    is_test_context = testing or os.getenv("TESTING") == "1" or "PYTEST_CURRENT_TEST" in os.environ
    logger.debug(
        "App context detection: testing=%r pytest_current_test=%s is_test_context=%s",
        os.getenv("TESTING"),
        "PYTEST_CURRENT_TEST" in os.environ,
        is_test_context,
    )

    is_development = ENVIRONMENT == "development"

    app = FastAPI(
        title="SanskritiSetu AI Agent Platform",
        description="Enterprise multi-tenant AI agent orchestration platform",
        version="2.0.0",
        lifespan=None if is_test_context else app_lifespan,
        debug=is_development and not testing,
        docs_url="/docs" if is_development else None,
        redoc_url="/redoc" if is_development else None,
        openapi_url="/openapi.json" if is_development else None,
    )

    # Configure middleware stack (CORRECT LIFO order handled internally)
    # 1st: Set tenant context (runs last due to LIFO)
    # 4th: Metrics (runs first, wraps everything)
    setup_middleware(app)

    logger.info("=== ACTIVE MIDDLEWARES ===")
    for m in app.user_middleware:
        logger.info(f"Middleware: {m.cls.__name__}")  # type: ignore[attr-defined]
    logger.info("==========================")

    # Register custom exception handlers (Sprint 3.3)
    register_exception_handlers(app)

    # Register all API routers synchronously before ASGI stack starts (ADR-033).
    # test context uses create_test_app() which registers routers separately.
    if not is_test_context:
        from src.core.api.router_registry import register_all_routers

        register_all_routers(app)

    return app


def create_test_app(
    db_session_override: Callable[..., Any]
    | None = None,  # TODO(TYPE): replace Any with concrete type
    tenant_context_override: Callable[..., Any]
    | None = None,  # TODO(TYPE): replace Any with concrete type
    include_routers: list[str]
    | None = None,  # TODO(SP-VOLGENDE): parameter doorgegeven maar niet verwerkt in create_app()
) -> FastAPI:
    """
    Create a test application with common overrides pre-configured.

    This is the canonical test bootstrap surface. It delegates to
    create_app(testing=True) and applies test-specific wiring.

    Args:
        db_session_override: Custom database session dependency
        tenant_context_override: Custom tenant context dependency
        include_routers: List of router names to include (None = all)

    Returns:
        Test-configured FastAPI application
    """
    test_app = create_app(testing=True)
    wire_container()
    from src.core.api.router_registry import register_all_routers

    register_all_routers(test_app)

    # Initialize FeatureFlagManager for testing
    from src.core.feature_flags import FeatureFlagManager

    test_app.state.ff_manager = FeatureFlagManager()

    @test_app.exception_handler(HTTPException)
    async def test_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        path = request.url.path.lower()
        if "/auth" not in path:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

        if isinstance(exc.detail, dict) and "error" in exc.detail:
            content = exc.detail
        else:
            content = {"error": {"message": str(exc.detail)}}

        return JSONResponse(status_code=exc.status_code, content=content)

    from src.core.exceptions.exceptions import SanskritiError

    @test_app.exception_handler(SanskritiError)
    async def test_sanskriti_error_handler(request: Request, exc: SanskritiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": exc.message,
                    "error_code": exc.error_code,
                    "status_code": exc.status_code,
                    "details": exc.details,
                },
                "message": exc.message,
            },
        )

    # Apply dependency overrides
    if db_session_override:
        from src.core.api.dependencies import get_db as dep_get_db
        from src.core.auth import dependencies as auth_dependencies_module
        from src.core.database.database import get_async_session as database_get_async_session
        from src.core.database.database import get_db as database_get_db

        test_app.dependency_overrides[dep_get_db] = db_session_override
        test_app.dependency_overrides[database_get_db] = db_session_override
        test_app.dependency_overrides[database_get_db] = db_session_override
        test_app.dependency_overrides[database_get_async_session] = db_session_override
        test_app.dependency_overrides[auth_dependencies_module.get_db] = db_session_override
        test_app.dependency_overrides[database_get_async_session] = db_session_override

    if tenant_context_override:
        from src.core.container import get_tenant_context

        test_app.dependency_overrides[get_tenant_context] = tenant_context_override

    return test_app


app = create_app()


# =============================================================================
# METRICS ENDPOINT
# =============================================================================


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type="text/plain")


# =============================================================================
# DEVELOPMENT SERVER
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",  # nosec B104: Docker networking (Traefik secures)
        port=8000,
        log_level="info",
    )
