# dsm:exempt reason: bootstrap -- middleware-configuratie draait voor de eerste request
import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.middleware.performance_profiler import PerformanceProfilingMiddleware
from src.core.middleware.audit_middleware import AuditLoggingMiddleware
from src.core.middleware.max_body_size_middleware import MaxRequestBodySizeMiddleware
from src.core.database.session import get_db_session
from src.core.middleware.quota_middleware import TenantQuotaMiddleware
from src.core.middleware.security_headers import SecurityHeadersMiddleware
from src.core.middleware.tenant_middleware import TenantMiddleware
from src.core.observability.metrics import PrometheusMiddleware
from src.core.security.security_middleware import SecurityMiddleware


class ProbeBypassMiddleware:
    """Pure ASGI middleware -- short-circuits /health and /status before any other
    middleware or route handler runs. Avoids BaseHTTPMiddleware stream issues."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path == "/health":
                response = JSONResponse(
                    status_code=200,
                    content={
                        "status": "ok",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                await response(scope, receive, send)
                return
            if path == "/status":
                from src.core.api.setup.app_state import app_state

                response = JSONResponse(
                    status_code=200,
                    content={
                        "status": "operational",
                        "database_initialized": bool(app_state.get("database_initialized", False)),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


from src.core.shared.config import get_settings

logger = logging.getLogger(__name__)


def setup_middleware(
    app: FastAPI,
    security_available: bool = False,
    metrics_middleware_available: bool = False,
) -> None:
    """
    Configures all middleware for the FastAPI application in correct LIFO order.

    Request Flow (Execution Order):
    1. Security Middleware (IP allowlist, rate limiting, threat detection)
    2. Security Headers (Added after, Executed before)
    3. HTTPS Redirect (production only)
    4. GZip Compression
    5. Tenant & Quota Middleware
    6. Performance Profiling & Metrics
    7. Tool Broker Metrics (optional)
    8. CORS (Added Last, Executed First)
    """
    settings = get_settings()
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()

    logger.info(f"Configuring middleware stack for {ENVIRONMENT} environment...")

    # === 1. Security Middleware (IP validation, rate limiting, threat detection) ===
    enable_security = os.getenv("ENABLE_SECURITY_MIDDLEWARE", "true").lower() not in (
        "false",
        "0",
        "off",
        "no",
    )
    app.add_middleware(SecurityMiddleware, enable_security=enable_security)
    logger.info(f"Security middleware registered with enable_security={enable_security}")

    # === 2. Security Headers (Added First, Executed Last) ===
    app.add_middleware(SecurityHeadersMiddleware)
    logger.debug("Security headers middleware added")

    # === 3. HTTPS Redirect (Production Only) ===
    if os.getenv("FORCE_HTTPS", "false").lower() == "true":
        app.add_middleware(HTTPSRedirectMiddleware)
        logger.info("HTTPS redirect middleware enabled")

    # === 4. GZip Compression ===
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    logger.debug("GZip compression added")

    # === 6. Observability Layer ===
    app.add_middleware(PerformanceProfilingMiddleware)
    app.add_middleware(PrometheusMiddleware)
    logger.debug("Observability middleware added")

    # === [AUDIT LOGGING] ===
    app.add_middleware(
        AuditLoggingMiddleware,
        log_to_db=(ENVIRONMENT == "production"),
        db_session_factory=get_db_session,  # type: ignore[arg-type]
    )
    logger.debug("Audit logging middleware added")

    # === 5. Tenant & Quota Layer ===
    # Quota depends on Tenant context being set
    app.add_middleware(TenantQuotaMiddleware)
    app.add_middleware(TenantMiddleware)
    logger.debug("Tenant and quota middleware added")

    # === 7. Tool Broker Metrics (Optional) ===
    if metrics_middleware_available:
        try:
            from src.core.middleware.metrics_middleware import ToolBrokerMetricsMiddleware

            app.add_middleware(
                ToolBrokerMetricsMiddleware,
                skip_paths=["/health", "/metrics", "/docs", "/redoc", "/openapi.json"],
            )
            logger.info("Tool Broker Metrics Middleware registered")
        except ImportError:
            pass

    # === 8. CORS (Added Last, Executed First) ===
    from src.core.middleware.security_headers import get_cors_config, validate_cors_config
    from src.core.middleware.websocket_cors import WebSocketCORSMiddleware

    cors_config = get_cors_config(ENVIRONMENT)
    validate_cors_config(cors_config, ENVIRONMENT)

    # WebSocket CORS: Starlette's CORSMiddleware does not add CORS headers to
    # WebSocket rejection responses (400/403). This custom middleware fills that gap.
    app.add_middleware(
        WebSocketCORSMiddleware,
        allowed_origins=cors_config["allow_origins"],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config["allow_origins"],
        allow_credentials=cors_config["allow_credentials"],
        allow_methods=cors_config["allow_methods"],
        allow_headers=cors_config["allow_headers"],
        expose_headers=cors_config.get("expose_headers", []),
        max_age=cors_config.get("max_age", 600),
    )
    logger.info(f"CORS configured for {ENVIRONMENT} (Strict Mode)")

    # === 9. Probe bypass (OUTERMOST until the body-size guard below) ===
    # Pure ASGI -- short-circuits /health and /status before any other middleware.
    app.add_middleware(ProbeBypassMiddleware)
    logger.debug("Probe bypass middleware added")

    # === 10. Max request body size (LAST = TRUE OUTERMOST) ===
    # Pure ASGI -- counts received body bytes before ANY other middleware or FastAPI's own
    # request.form()/solve_dependencies() touches them (BE-AGT-060 dag 3 Gate 2, security-
    # review finding 1: a multipart file part is otherwise fully buffered before auth runs).
    # Explicitly the SAME setting documents/upload_router.py already uses -- this is a vangnet
    # ABOVE the endpoint-eigen cap, not a new, separate (and possibly stricter) one.
    app.add_middleware(MaxRequestBodySizeMiddleware, max_bytes=settings.max_upload_size_bytes)
    logger.debug("Max request body size middleware added (outermost)")

    logger.info("Middleware configuration complete.")
