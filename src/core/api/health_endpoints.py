# orphan:exempt -- legacy flat file, replaced by src/core/api/v1/health/ (SP-API-004 Dag 4); still imported by v1/health sub-routers
"""
Health Check Endpoints - Context7 Best Practice

Source: /websites/fastapi_tiangolo
Pattern: Three-tier health checks for Kubernetes
- /health - Liveness probe (basic container health) - < 50ms
- /health/ready - Readiness probe (dependencies check) - < 500ms
- /health/db - Detailed diagnostics (pool stats) - < 3s, AUTH REQUIRED

ADR-012 Implementation with:
- Explicit timeouts (DB: 300ms, Redis: 100ms)
- Rate limiting (public: 100/min, ready: 30/min, db: 10/min)
- Graceful degradation (503 on failure, degraded on slow)
- Authentication on sensitive endpoints
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, TypeVar, cast
from collections.abc import Callable

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import src.core.caching.cache_layer as cache_layer_module
get_cache = cache_layer_module.get_cache
import src.core.database.database as db_module
db_manager = db_module.db_manager
get_db = db_module.get_db
from src.core.events import get_event_consumer, get_pubsub_manager

logger = logging.getLogger(__name__)

# =============================================================================
# ADR-012 TIMEOUT CONFIGURATION
# =============================================================================

READINESS_TIMEOUT_DB = 0.3  # 300ms (revised from 200ms - too strict under load)
READINESS_TIMEOUT_REDIS = 0.1  # 100ms
HEALTH_DB_QUERY_TIMEOUT = 1.0  # 1s for diagnostics query
HEALTH_DB_POOL_TIMEOUT = 0.5  # 500ms for pool stats
HEALTH_DB_MIGRATION_TIMEOUT = 0.5  # 500ms for migration check

# Degraded thresholds (warning, not failure)
DB_DEGRADED_THRESHOLD_MS = 200  # >200ms = degraded but still 200
REDIS_DEGRADED_THRESHOLD_MS = 50  # >50ms = degraded

# =============================================================================
# RATE LIMITING
# =============================================================================

# Import from existing rate limiter middleware
from src.core.middleware.rate_limiter import get_limiter

# Get the rate limiter instance
limiter = get_limiter("health")


F = TypeVar("F", bound=Callable[..., Any])  # TODO(TYPE): replace Any with concrete type


# Decorator factory for health endpoint rate limits
def health_rate_limit(requests: str) -> Callable[[F], F]:
    """Create rate limit decorator for health endpoints.

    Args:
        requests: Rate limit string, e.g., "100/minute", "30/minute"
    """
    return cast(Callable[[F], F], limiter.limit(requests))


# =============================================================================
# AUTHENTICATION
# =============================================================================

from src.core.api.dependencies import require_authenticated_user

# Use the existing authentication dependency
verify_token = require_authenticated_user


class LLMProviderStatus(BaseModel):
    """Status of an LLM provider"""

    name: str
    available: bool
    configured: bool
    error: str | None = None


class LLMHealthResponse(BaseModel):
    """LLM system health response"""

    status: str  # "operational", "degraded", "unavailable"
    providers: dict[str, LLMProviderStatus]
    default_provider: str | None = None
    message: str


router = APIRouter()


from fastapi.responses import JSONResponse


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> JSONResponse:
    """
    Liveness probe: Is the service process running?

    ADR-012: Must respond within 50ms (hard limit: 100ms)
    Used by Kubernetes liveness probe - basic container health only.
    Does NOT check dependencies to avoid cascading failures.

    NOTE: No rate limiting -- rate limiter uses Redis in production and
    would itself be a dependency that could cause cascading 500s, violating ADR-012.
    """
    return JSONResponse(
        content={
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.get("/health/ready", status_code=status.HTTP_200_OK)
@health_rate_limit("30/minute")  # 30/min - readiness is more expensive
async def readiness_check(
    request: Request, response: Response
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Readiness probe: Is the service ready to accept traffic?

    ADR-012: Must respond within 500ms
    Used by Kubernetes readiness probe - checks critical dependencies.
    Returns 503 if critical dependencies are down (removes pod from load balancer).
    Returns 200 with 'degraded' status if slow but functional.

    Timeouts:
    - Database: 300ms (revised from 200ms - too strict under load)
    - Redis: 100ms

    Rate limited: 30 requests/minute per client
    """
    dependencies: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    critical_failures: list[str] = []
    degraded_services: list[str] = []

    # Check Database Manager Initialization State FIRST
    if not db_manager.is_initialized():
        dependencies["database"] = "not_initialized"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "reason": "Database manager not initialized",
                "dependencies": dependencies,
            },
        )

    # Check database connection with timeout
    db_start = time.time()
    try:
        db_result = await asyncio.wait_for(
            db_manager.health_check(),
            timeout=READINESS_TIMEOUT_DB,
        )
        db_time = (time.time() - db_start) * 1000

        if not db_result:
            dependencies["database"] = "unhealthy"
            critical_failures.append("database")
        elif db_time > DB_DEGRADED_THRESHOLD_MS:
            # Degraded but still functional
            dependencies["database"] = f"degraded ({db_time:.0f}ms)"
            degraded_services.append("database")
        else:
            dependencies["database"] = "connected"
    except TimeoutError:
        dependencies["database"] = "timeout"
        critical_failures.append("database")
    except Exception as e:
        dependencies["database"] = f"error: {type(e).__name__}"
        critical_failures.append("database")

    # Check Redis connection with timeout
    redis_start = time.time()
    try:
        cache = await get_cache()
        redis_client = getattr(cache, "redis_client", None)

        if redis_client is not None:
            await asyncio.wait_for(
                redis_client.ping(),
                timeout=READINESS_TIMEOUT_REDIS,
            )
            redis_time = (time.time() - redis_start) * 1000

            if redis_time > REDIS_DEGRADED_THRESHOLD_MS:
                # Degraded but still functional
                dependencies["redis"] = f"degraded ({redis_time:.0f}ms)"
                degraded_services.append("redis")
            else:
                dependencies["redis"] = "connected"
        else:
            dependencies["redis"] = "not_connected"
            critical_failures.append("redis")
    except TimeoutError:
        dependencies["redis"] = "timeout"
        critical_failures.append("redis")
    except Exception as e:
        dependencies["redis"] = f"error: {type(e).__name__}"
        critical_failures.append("redis")

    # Return 503 if critical dependencies failed
    if critical_failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "reason": f"Critical dependencies failed: {', '.join(critical_failures)}",
                "dependencies": dependencies,
            },
        )

    # Return degraded status if slow but functional
    if degraded_services:
        return {
            "status": "degraded",
            "reason": f"Slow dependencies: {', '.join(degraded_services)}",
            "dependencies": dependencies,
        }

    return {"status": "ready", "dependencies": dependencies}


async def _get_migration_status_with_timeout(
    timeout: float,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get Alembic migration status with timeout."""
    try:
        # Get current DB revision
        async with db_manager.get_session() as session:
            result = await asyncio.wait_for(
                session.execute(text("SELECT version_num FROM alembic_version")),
                timeout=timeout,
            )
            current = result.scalar()

        # Get latest file revision (this is sync, but fast)
        try:
            from alembic.config import Config
            from alembic.script import ScriptDirectory

            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            head = script.get_current_head()

            return {
                "current": current,
                "head": head,
                "is_current": current == head,
            }
        except Exception as e:
            logger.error("_get_migration_status_with_timeout mislukt: %s: %s", type(e).__name__, e, exc_info=True)
            return {"current": current, "error": "Could not read alembic head"}

    except TimeoutError:
        return {"error": "timeout", "message": "Migration status check timed out"}
    except Exception as e:
        return {"error": type(e).__name__, "message": "Er is een fout opgetreden."}


@router.get("/health/db", status_code=status.HTTP_200_OK)
@health_rate_limit("10/minute")  # 10/min - expensive endpoint
async def db_health_check(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    authenticated: bool = Depends(verify_token),  # AUTH REQUIRED
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Database health with connection pool stats and migration status.

    ADR-012: Must respond within 3s (hard limits: query 1s, pool 0.5s, migration 0.5s)
    Detailed diagnostics endpoint for monitoring dashboards.

    WARNING: Contains internal information (tenant count, pool stats).
    Authentication required.

    Timeouts:
    - Query: 1s (returns truncated if exceeded)
    - Pool stats: 0.5s
    - Migration status: 0.5s

    Rate limited: 10 requests/minute per client
    """
    # Query with timeout
    tenant_count: int | None = None
    try:
        result = await asyncio.wait_for(
            db.execute(text("SELECT COUNT(*) FROM tenants")),
            timeout=HEALTH_DB_QUERY_TIMEOUT,
        )
        tenant_count = result.scalar() or 0
    except TimeoutError:
        tenant_count = None  # Truncated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'Database query failed: {type(e).__name__}',
        )

    # Get pool stats with timeout
    pool_stats: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    try:
        if db.bind is not None:
            from sqlalchemy.ext.asyncio import AsyncEngine

            engine = db.bind
            if isinstance(engine, AsyncEngine):
                pool = getattr(engine.sync_engine, "pool", None)
                if pool is not None:
                    size_method = getattr(pool, "size", None)
                    if callable(size_method):
                        pool_size: int = cast(int, size_method())
                        checked_in_method = getattr(pool, "checkedin", None)
                        checked_in: int = (
                            cast(int, checked_in_method()) if callable(checked_in_method) else 0
                        )
                        overflow_method = getattr(pool, "overflow", None)
                        overflow: int = (
                            cast(int, overflow_method()) if callable(overflow_method) else 0
                        )
                        pool_stats = {
                            "size": pool_size,
                            "checked_in": checked_in,
                            "checked_out": pool_size - checked_in,
                            "overflow": overflow,
                            "utilization": (
                                round((pool_size - checked_in) / pool_size * 100, 2)
                                if pool_size > 0
                                else 0
                            ),
                        }
    except TimeoutError:
        pool_stats = {"status": "timeout"}
    except Exception as e:
        pool_stats = {"status": "error", "error": type(e).__name__}

    # Get migration status with timeout
    migration_status = await _get_migration_status_with_timeout(HEALTH_DB_MIGRATION_TIMEOUT)

    # Determine overall status
    if tenant_count is None:
        overall_status = "degraded"
    elif pool_stats.get("status") in ["timeout", "error"]:
        overall_status = "degraded"
    else:
        overall_status = "healthy"

    return {
        "status": overall_status,
        "tenant_count": tenant_count,
        "pool": pool_stats if pool_stats else {"status": "pool_stats_unavailable"},
        "migrations": migration_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", status_code=status.HTTP_200_OK, deprecated=True)
async def readiness_check_legacy(
    request: Request, response: Response
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    DEPRECATED: Use /health/ready instead.
    Legacy endpoint for backward compatibility.
    """
    return await readiness_check(request=request, response=response)


@router.get("/health/deep", status_code=status.HTTP_200_OK)
@health_rate_limit("10/minute")  # 10/min - expensive endpoint
async def deep_health_check(
    request: Request,
    response: Response,
    authenticated: bool = Depends(verify_token),  # AUTH REQUIRED
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Deep health check: Comprehensive system diagnostics.

    WARNING: Contains detailed internal information.
    Authentication required.

    Checks all critical and non-critical dependencies:
    - Database (critical)
    - Redis (critical)
    - Event consumer/Redis Pub/Sub (non-critical)
    - Sync-server (for YJS collaboration)

    Returns detailed status for monitoring dashboards.

    Rate limited: 10 requests/minute per client
    """
    checks: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    overall_status = "healthy"
    critical_failures: list[str] = []

    # 1. Database Check with timeout
    try:
        db_result = await asyncio.wait_for(
            db_manager.health_check() if db_manager.is_initialized() else asyncio.sleep(0),
            timeout=READINESS_TIMEOUT_DB,
        )
        if db_result:
            checks["database"] = {"status": "healthy", "critical": True}
        else:
            checks["database"] = {"status": "unhealthy", "critical": True}
            overall_status = "degraded"
            critical_failures.append("database")
    except TimeoutError:
        checks["database"] = {"status": "timeout", "critical": True}
        overall_status = "degraded"
        critical_failures.append("database")
    except Exception as e:
        checks["database"] = {"status": f"error: {type(e).__name__}", "critical": True}
        overall_status = "degraded"
        critical_failures.append("database")

    # 2. Redis Check with timeout
    try:
        cache = await get_cache()
        redis_client = getattr(cache, "redis_client", None)
        if redis_client is not None:
            await asyncio.wait_for(redis_client.ping(), timeout=READINESS_TIMEOUT_REDIS)
            checks["redis"] = {"status": "healthy", "critical": True}
        else:
            checks["redis"] = {"status": "not_connected", "critical": True}
            overall_status = "degraded"
            critical_failures.append("redis")
    except TimeoutError:
        checks["redis"] = {"status": "timeout", "critical": True}
        overall_status = "degraded"
        critical_failures.append("redis")
    except Exception as e:
        checks["redis"] = {"status": f"error: {type(e).__name__}", "critical": True}
        overall_status = "degraded"
        critical_failures.append("redis")

    # 3. Event Consumer Check (Redis Pub/Sub)
    try:
        event_consumer = await get_event_consumer()

        if cast(Any, event_consumer)._connected:  # TODO(TYPE): replace Any with concrete type
            stats = await event_consumer.get_stats()
            checks["event_consumer"] = {
                "status": "healthy",
                "critical": False,
                "mode": stats.get("mode", "redis_pubsub"),
                "consumers": stats.get("total_handlers", 0),
                "connected": stats.get("connected", False),
            }
        else:
            checks["event_consumer"] = {"status": "not_connected", "critical": False}
            if overall_status == "healthy":
                overall_status = "degraded"
    except Exception as e:
        logger.error("deep_health_check mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        checks["event_consumer"] = {"status": "error", "critical": False}

    # 4. Sync-server Check (WebSocket/YJS)
    try:
        sync_server_url = os.getenv("SYNC_SERVER_URL", "http://sync-server:1234")

        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            client_response = await session.get(f"{sync_server_url}/health")
            if client_response.status == 200:
                checks["sync_server"] = {"status": "healthy", "critical": False}
            else:
                checks["sync_server"] = {
                    "status": f"unhealthy (HTTP {client_response.status})",
                    "critical": False,
                }
                if overall_status == "healthy":
                    overall_status = "degraded"
    except Exception as e:
        logger.error("deep_health_check mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        checks["sync_server"] = {"status": "unreachable", "critical": False}
        if overall_status == "healthy":
            overall_status = "degraded"

    # 5. Event System Check (FASE 6.1)
    try:
        pubsub = await get_pubsub_manager()

        if pubsub.connected:
            stats = await pubsub.get_stats()
            checks["event_system"] = {
                "status": "healthy",
                "critical": False,
                "subscribers": stats.get("subscribed_channels", 0),
                "handlers": stats.get("total_handlers", 0),
            }
        else:
            checks["event_system"] = {"status": "not_connected", "critical": False}
    except Exception as e:
        logger.error("deep_health_check mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        checks["event_system"] = {"status": "error", "critical": False}

    # 6. Digital Twin subsystem check (ADR-025/026)
    try:
        from src.core.learning.health.twin_health import run_twin_health

        cache = await get_cache()
        redis_client = getattr(cache, "redis_client", None)
        async with db_manager.get_session() as twin_db:
            twin_result = await run_twin_health(twin_db, redis_client)
        checks["twin_subsystem"] = {
            "status": twin_result["status"],
            "critical": False,
            "checks": twin_result.get("checks", {}),
        }
        if twin_result["status"] == "error" and overall_status == "healthy":
            overall_status = "degraded"
    except Exception as e:
        checks["twin_subsystem"] = {"status": f"error: {type(e).__name__}", "critical": False}

    # Determine HTTP status code
    if critical_failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "message": f"Critical services down: {', '.join(critical_failures)}",
                "checks": checks,
            },
        )

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "critical_services": len([c for c in checks.values() if c.get("critical")]),
        "healthy_services": len([c for c in checks.values() if c["status"] == "healthy"]),
    }


# =============================================================================
# PAPERCLIP PIPELINE HEALTH CHECK
# =============================================================================


async def check_registry() -> bool:
    """Check DomainPackRegistry health by calling get_active_packs()."""
    try:
        from src.core.container import container

        registry = container.domain_pack_registry()
        # Call with dummy tenant_id - we just want to check if the method works
        await registry.get_active_packs(tenant_id=1)
        return True
    except Exception:
        return False


async def check_scorer() -> bool:
    """Check PackActivationScorer health by creating an instance."""
    try:
        from src.core.container import container

        scorer = container.pack_activation_scorer()
        return scorer is not None
    except Exception:
        return False


async def check_validator() -> bool:
    """Check GoalAlignmentValidator health by creating an instance."""
    try:
        from src.core.container import container

        validator = container.goal_alignment_validator()
        return validator is not None
    except Exception:
        return False


async def check_audit_log_table() -> bool:
    """Check PackActivationAuditLog table health by counting records."""
    try:
        from sqlalchemy import func, select

        from src.core.company.models import PackActivationAuditLog
        from src.core.container import container

        db_manager = container.database_manager()
        async with db_manager.get_session() as session:
            result = await session.execute(select(func.count()).select_from(PackActivationAuditLog))
            count = result.scalar()
            return count is not None  # Table exists and is queryable
    except Exception:
        return False


@router.get("/health/paperclip")
async def paperclip_health() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Paperclip Pipeline Health Check.

    Validates the Paperclip pipeline components:
    - DomainPackRegistry: Can fetch active packs
    - PackActivationScorer: Scoring service available
    - GoalAlignmentValidator: Alignment validation available
    - AuditLog table: Database table accessible

    Returns healthy status only if all checks pass.
    """
    checks = {
        "domain_pack_registry": await check_registry(),
        "pack_activation_scorer": await check_scorer(),
        "goal_alignment_validator": await check_validator(),
        "audit_log_table": await check_audit_log_table(),
    }
    healthy = all(checks.values())
    return {"status": "healthy" if healthy else "unhealthy", "checks": checks}


@router.get("/llm", response_model=LLMHealthResponse)
async def llm_health_check() -> LLMHealthResponse:
    """
    LLM Provider Health Status: Check which LLM providers are configured and available.
    Returns detailed status of all configured providers (Deepseek, Google Gemini, OpenAI, Ollama).
    """
    providers: dict[str, LLMProviderStatus] = {}
    default_provider = None
    overall_status = "unavailable"

    # Check Deepseek availability
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        providers["deepseek"] = LLMProviderStatus(
            name="Deepseek", available=True, configured=True, error=None
        )
        if not default_provider:
            default_provider = "deepseek"
        overall_status = "operational"
    else:
        providers["deepseek"] = LLMProviderStatus(
            name="Deepseek",
            available=False,
            configured=False,
            error="DEEPSEEK_API_KEY not configured",
        )

    # Check Google Gemini availability
    google_key = os.getenv("GOOGLE_API_KEY")
    if google_key:
        providers["google"] = LLMProviderStatus(
            name="Google Gemini", available=True, configured=True, error=None
        )
        if not default_provider:
            default_provider = "google"
            overall_status = "operational"
    else:
        providers["google"] = LLMProviderStatus(
            name="Google Gemini",
            available=False,
            configured=False,
            error="GOOGLE_API_KEY not configured",
        )

    # Check OpenAI availability
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        providers["openai"] = LLMProviderStatus(
            name="OpenAI", available=True, configured=True, error=None
        )
        if not default_provider:
            default_provider = "openai"
            overall_status = "operational"
    else:
        providers["openai"] = LLMProviderStatus(
            name="OpenAI",
            available=False,
            configured=False,
            error="OPENAI_API_KEY not configured",
        )

    # Check Anthropic availability
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        providers["anthropic"] = LLMProviderStatus(
            name="Anthropic Claude", available=True, configured=True, error=None
        )
        if not default_provider:
            default_provider = "anthropic"
            overall_status = "operational"
    else:
        providers["anthropic"] = LLMProviderStatus(
            name="Anthropic Claude",
            available=False,
            configured=False,
            error="ANTHROPIC_API_KEY not configured",
        )

    # Check Ollama availability
    ollama_client = None
    try:
        import src.core.llm.ollama_client as ollama_module

        ollama_client = ollama_module.RobustOllamaClient()
        ollama_health = await ollama_client.health_check()

        if ollama_health.get("healthy"):
            model_count = ollama_health.get("model_count", 0)
            providers["ollama"] = LLMProviderStatus(
                name="Ollama (Local)",
                available=True,
                configured=True,
                error=None if model_count > 0 else "No models loaded",
            )
        else:
            error = ollama_health.get("error", "Unknown error")
            providers["ollama"] = LLMProviderStatus(
                name="Ollama (Local)",
                available=False,
                configured=True,
                error=f"Unreachable: {error}",
            )
    except Exception as e:
        logger.error("llm_health_check mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        providers["ollama"] = LLMProviderStatus(
            name="Ollama (Local)",
            available=False,
            configured=True,
            error="Error",
        )

    if ollama_client is not None:
        await ollama_client.close()

    # Determine overall status
    if not default_provider:
        overall_status = "unavailable"
        message = "No LLM providers configured"
    elif len([p for p in providers.values() if p.available]) == 1:
        message = f"Single provider operational: {default_provider}"
    else:
        message = f"Multiple providers available (using {default_provider} as default)"

    return LLMHealthResponse(
        status=overall_status,
        providers=providers,
        default_provider=default_provider,
        message=message,
    )
