"""
App Factory - DEPRECATED: Use src.main.create_app() or src.main.create_test_app().

This module is kept for backward compatibility during the migration to
src.main as the single bootstrap surface. All new code should import from
src.main instead.

Migration:
    from src.core.app_factory import create_app
    -> from src.main import create_app

    from src.core.app_factory import create_test_app
    -> from src.main import create_test_app

Created: 2025-12-06
Deprecated: 2026-04-30
"""

import logging
import os
import warnings
from contextlib import asynccontextmanager
from typing import Any, cast
from collections.abc import AsyncGenerator, Awaitable, Callable

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from src.core.container import container, get_db, get_tenant_context
from src.core.middleware.rate_limiter import get_limiter, rate_limit_exceeded_handler
from src.core.monitoring.tracing import initialize_tracing


from src.core.shared.environment import is_development as _is_development
from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord


logger = logging.getLogger(__name__)

warnings.warn(
    "src.core.app_factory is deprecated. Use src.main.create_app() or src.main.create_test_app() instead.",
    DeprecationWarning,
    stacklevel=2,
)

# ============================================================================
# ROUTER REGISTRY
# ============================================================================


def get_default_routers() -> list[
    tuple[Any, str, list[str]]  # TODO(TYPE): replace Any with concrete type
]:  # TODO(TYPE): replace Any with concrete type
    """
    Get list of default routers to include.

    Returns list of (router, prefix, tags) tuples.
    Lazy imports to avoid circular dependencies.
    """
    routers: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    try:
        from src.core.api.auth.router import router as auth_router

        # Register auth router once to avoid duplicate route registration.
        routers.append((auth_router, "/api/v1", ["Authentication"]))
    except ImportError as e:
        logger.warning(f"Could not import auth router: {e}")

    try:
        from src.core.api.workflow_endpoints import router as workflow_router  # type: ignore[attr-defined]

        routers.append((workflow_router, "", ["Workflows"]))
    except ImportError as e:
        logger.warning(f"Could not import workflow_endpoints: {e}")

    try:
        from src.core.api.agent_endpoints import router as agent_router

        routers.append((agent_router, "", ["Agents"]))
    except ImportError as e:
        logger.warning(f"Could not import agent_endpoints: {e}")

    try:
        from src.core.api.admin_endpoints import router as admin_router  # type: ignore[attr-defined]

        routers.append((admin_router, "", ["Admin"]))
    except ImportError as e:
        logger.debug(f"Could not import admin_endpoints: {e}")

    # Tenant management -- migrated to src.core.api.v1.tenants/ (AUDIT-DB-01).
    # Legacy v1/tenant_management/ router is no longer registered here to avoid
    # route collision with the new tenants registry; app_factory is deprecated.
    # Canonical registration happens via src.core.api.router_registry in src.main.

    try:
        from src.core.api.v1.user_management import domain_router as user_domain_router

        routers.append((user_domain_router, "", ["User Management"]))
    except ImportError as e:
        logger.debug("Could not import user_management domain router: %s", e)

    try:
        from src.core.api.events_endpoints import router as events_router

        routers.append((events_router, "/v1", ["Events"]))
    except ImportError as e:
        logger.warning(f"Could not import events_endpoints: {e}")

    try:
        from src.core.api.workflow_visualization_endpoints import router as viz_router  # type: ignore[attr-defined]

        routers.append((viz_router, "/api/v1", ["Visualization"]))
    except ImportError as e:
        logger.warning(f"Could not import workflow_visualization_endpoints: {e}")

    try:
        from src.core.api.v1.focus_builder.proxy import get_focus_builder_router

        focus_builder_router = get_focus_builder_router()
        routers.append((focus_builder_router, "/api/v1", ["Focus Builder"]))
    except ImportError as e:
        logger.warning(f"Could not import focus_builder_endpoints: {e}")

    try:
        from src.core.api.tool_endpoints import router as tool_router

        routers.append((tool_router, "/api/v1", ["Tools"]))
    except ImportError as e:
        logger.warning(f"Could not import tool_endpoints: {e}")

    try:
        from src.core.api.tool_broker_endpoints import router as tool_broker_router  # type: ignore[attr-defined]

        routers.append((tool_broker_router, "", ["Tool Broker"]))
    except ImportError as e:
        logger.warning(f"Could not import tool_broker_endpoints: {e}")

    try:
        from src.core.api.prediction_endpoints import prediction_router  # type: ignore[attr-defined]

        routers.append((prediction_router, "", ["Phase5-Prediction"]))
    except ImportError as e:
        logger.warning(f"Could not import prediction_endpoints: {e}")

    try:
        from src.core.api.models_endpoints import router as models_registry_router  # type: ignore[attr-defined]

        routers.append((models_registry_router, "", ["Model Registry"]))
    except ImportError as e:
        logger.warning(f"Could not import models_endpoints: {e}")

    try:
        from src.core.api.template_endpoints import router as template_router

        routers.append((template_router, "", ["Workflow Templates"]))
    except ImportError as e:
        logger.warning(f"Could not import template_endpoints: {e}")

    try:
        from src.core.api.workflow_builder_endpoints import router as builder_router

        routers.append((builder_router, "", ["Workflow Builder"]))
    except ImportError as e:
        logger.warning(f"Could not import workflow_builder_endpoints: {e}")

    try:
        from src.core.api.webhooks.activepieces_handler import router as ap_webhook_router

        routers.append((ap_webhook_router, "/api/v1", ["Webhooks"]))
    except ImportError as e:
        logger.warning(f"Could not import activepieces_handler: {e}")

    try:
        from src.api.v1.endpoints.agent import router as agentic_router

        routers.append((agentic_router, "/api/v1", ["Agent"]))
    except ImportError as e:
        logger.warning(f"Could not import agentic agent router: {e}")

    try:
        from src.core.api.autonomous_endpoints import router as autonomous_router

        routers.append((autonomous_router, "", ["Autonomous"]))
    except ImportError as e:
        logger.warning(f"Could not import autonomous_endpoints: {e}")

    try:
        from src.core.api.evaluation_endpoints import router as evaluation_router

        routers.append((evaluation_router, "/api/v1", ["Evaluation"]))
    except ImportError as e:
        logger.warning(f"Could not import evaluation_endpoints: {e}")

    try:
        from src.core.api.cva_endpoints import router as cva_router  # type: ignore[attr-defined]

        routers.append((cva_router, "", ["CVA"]))
    except ImportError as e:
        logger.warning(f"Could not import cva_endpoints: {e}")

    try:
        from src.core.api.learning_endpoints import router as learning_router

        routers.append((learning_router, "", ["Learning"]))
    except ImportError as e:
        logger.warning(f"Could not import learning_endpoints: {e}")

    try:
        from src.core.api.monitoring_dashboard_endpoints import (
            router as monitoring_dashboard_router,
        )

        routers.append((monitoring_dashboard_router, "", ["Monitoring"]))
    except ImportError as e:
        logger.debug(f"Could not import monitoring_dashboard_endpoints: {e}")

    try:
        from src.core.api.monitoring_endpoints import router as monitoring_router  # type: ignore[attr-defined]

        routers.append((monitoring_router, "/api", ["Monitoring"]))
    except ImportError as e:
        logger.warning(f"Could not import monitoring_endpoints: {e}")

    try:
        from src.core.api.production_endpoints import router as production_router

        routers.append((production_router, "/api", ["Production"]))
    except ImportError as e:
        logger.warning(f"Could not import production_endpoints: {e}")

    try:
        from src.core.api.v1.websocket_hitl import router as hitl_ws_router

        routers.append((hitl_ws_router, "", ["HITL WebSocket"]))
    except ImportError as e:
        logger.debug(f"Could not import websocket_hitl: {e}")

    return routers


# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================


@asynccontextmanager
async def app_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager - handles startup/shutdown.

    Replaces deprecated @app.on_event("startup") pattern.
    """
    # Startup
    logger.info(f"Starting {app.title} v{app.version}")

    # Initialize database engine (lazy - only created when first accessed)
    try:
        engine = container.database_engine()
        logger.info(f"Database engine initialized: {database_url_zonder_wachtwoord(str(engine.url))}")
    except Exception as e:
        logger.error("Database initialization failed: %s: %s", type(e).__name__, e, exc_info=True)

    yield

    # Shutdown
    logger.info(f"Shutting down {app.title}")
    try:
        db_manager = container.database_manager()
        await db_manager.dispose()
    except Exception as e:
        logger.error("Database cleanup failed: %s: %s", type(e).__name__, e, exc_info=True)


# ============================================================================
# MIDDLEWARE FACTORIES
# ============================================================================


async def error_handler_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Global error handler middleware."""
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(f"Unhandled error: {e}")
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )


# ============================================================================
# APP FACTORY
# ============================================================================


def create_app(
    title: str = "SanskritiSetu",
    version: str = "2.0.0",
    description: str = "AI-Powered Cultural Heritage Platform",
    testing: bool = False,
    include_routers: list[str] | None = None,
    cors_origins: list[str]
    | None = None,  # TODO(SP-VOLGENDE): parameter geaccepteerd maar niet toegepast in CORS-config
    custom_lifespan: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> FastAPI:
    """
    Create a new FastAPI application instance.

    Args:
        title: Application title
        version: Application version
        description: API description
        testing: Enable testing mode (disables some middleware)
        include_routers: list[Any] of router names to include (None = all)  # TODO(TYPE): replace Any with concrete type
        cors_origins: list[Any] of allowed CORS origins  # TODO(TYPE): replace Any with concrete type
        custom_lifespan: Custom lifespan context manager

    Returns:
        Configured FastAPI application instance

    Example:
        # Production
        app = create_app()

        # Testing with specific routers
        app = create_app(testing=True, include_routers=["auth", "workflow"])

        # Custom configuration
        app = create_app(
            title="Test App",
            cors_origins=["http://localhost:3000"],
        )
    """
    # Use custom lifespan or default
    lifespan: Any | None = None  # TODO(TYPE): replace Any with concrete type
    if not testing:
        lifespan = custom_lifespan if custom_lifespan is not None else app_lifespan

    # Create FastAPI instance
    app = FastAPI(
        title=title,
        version=version,
        description=description,
        lifespan=lifespan,
        # Beide takken stonden hier op "/docs", dus de ternary suggereerde een keuze die er
        # niet was. Deze shim is deprecated en wordt door niets in src/ geimporteerd, maar een
        # app-object dat zijn schema onvoorwaardelijk publiceert is precies de tweede deur waar
        # ADR-036 OP-124 door terug kan komen.
        docs_url="/docs" if _is_development() else None,
        redoc_url="/redoc" if _is_development() else None,
        openapi_url="/openapi.json" if _is_development() else None,
    )

    # Store testing flag for middleware decisions
    app.state.testing = testing

    # Initialize rate limiter
    limiter = get_limiter()
    app.state.limiter = limiter

    # Add rate limit exception handler
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    # Initialize OpenTelemetry tracing (skip in testing mode)
    if not testing:
        try:
            initialize_tracing(app)
        except Exception as e:
            logger.warning(f"OpenTelemetry initialization skipped: {e}")

    # Note: CORS is configured in middleware_config.py via setup_middleware()
    # (called from main.py, not from this factory)

    # Add health endpoint (always available)
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Health check endpoint."""
        db_healthy = False
        try:
            db_manager = container.database_manager()
            db_healthy = await db_manager.health_check()
        except Exception:
            pass

        return {
            "status": "healthy" if db_healthy else "degraded",
            "database": "connected" if db_healthy else "disconnected",
            "version": version,
            "testing": testing,
        }

    # Add routers
    _include_routers(app, include_routers)

    # Wire DI container to this app's dependencies
    if not testing:
        try:
            container.wire(modules=["core.api.dependencies"])
        except Exception as e:
            logger.debug(f"Container wiring: {e}")

    logger.info(f"Created FastAPI app: {title} v{version} (testing={testing})")

    return app


def _include_routers(app: FastAPI, include_only: list[str] | None = None) -> None:
    """Include routers in application."""
    all_routers = get_default_routers()

    router_name_map = {
        "auth": "Authentication",
        "workflow": "Workflows",
        "agent": "Agents",
        "admin": "Admin",
        "tenant": "Tenants",
    }

    for router, prefix, tags in all_routers:
        # Check if we should include this router
        if include_only is not None:
            tag = tags[0] if tags else ""
            short_name = next((k for k, v in router_name_map.items() if v == tag), tag.lower())
            if short_name not in include_only and tag not in include_only:
                continue

        try:
            app.include_router(
                router,
                prefix=prefix,
                tags=cast(list[Any], tags),  # TODO(TYPE): replace Any with concrete type
            )  # TODO(TYPE): replace Any with concrete type
            logger.debug(f"Included router: {tags}")
        except Exception as e:
            logger.warning(f"Failed to include router {tags}: {e}")


# ============================================================================
# TEST APP FACTORY
# ============================================================================


def create_test_app(
    db_session_override: Callable[..., Any]
    | None = None,  # TODO(TYPE): replace Any with concrete type
    tenant_context_override: Callable[..., Any]
    | None = None,  # TODO(TYPE): replace Any with concrete type
    include_routers: list[str] | None = None,
) -> FastAPI:
    """
    Create a test application with common overrides pre-configured.

    Args:
        db_session_override: Custom database session dependency
        tenant_context_override: Custom tenant context dependency
        include_routers: list[Any] of router names to include  # TODO(TYPE): replace Any with concrete type

    Returns:
        Test-configured FastAPI application

    Example:
        @pytest.fixture
        def app(db_session):
            async def get_test_db():
                yield db_session

            return create_test_app(db_session_override=get_test_db)
    """
    app = create_app(
        title="SanskritiSetu (Test)",
        testing=True,
        include_routers=include_routers,
    )

    @app.exception_handler(HTTPException)
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

    @app.exception_handler(SanskritiError)
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
        from src.core.database.database import get_async_session as scope_get_async_session
        from src.core.database.database import get_db as database_get_db

        app.dependency_overrides[dep_get_db] = db_session_override
        app.dependency_overrides[get_db] = db_session_override
        app.dependency_overrides[database_get_db] = db_session_override
        app.dependency_overrides[database_get_async_session] = db_session_override
        app.dependency_overrides[auth_dependencies_module.get_db] = db_session_override
        app.dependency_overrides[scope_get_async_session] = db_session_override

    if tenant_context_override:
        app.dependency_overrides[get_tenant_context] = tenant_context_override

    return app


# ============================================================================
# SINGLETON FOR BACKWARD COMPATIBILITY
# ============================================================================

# DEPRECATED: Use create_app() instead
# This is only kept for backward compatibility during migration
_app_instance: FastAPI | None = None


def get_app() -> FastAPI:
    """
    DEPRECATED: Use create_app() for new code.

    Returns singleton app instance for backward compatibility.
    """
    global _app_instance
    if _app_instance is None:
        logger.warning("get_app() is deprecated - use create_app() instead")
        _app_instance = create_app()
    return _app_instance
