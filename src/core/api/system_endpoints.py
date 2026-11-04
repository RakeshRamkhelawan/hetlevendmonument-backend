# orphan:exempt -- legacy shim, pre-migration flat endpoint
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Body, Depends, Response

from src.core.api.setup.app_state import app_state
from src.core.auth.api_deps import get_current_user, UserResponse, require_scopes, OAuth2Scope

from src.core.monitoring.prometheus_metrics import get_metrics
from src.core.shared.config import get_feature_flag, get_settings

if TYPE_CHECKING:
    from src.core.caching.cache_layer import cached

# Import caching system if available
try:
    from src.core.caching.cache_layer import cache_layer as cache_system  # type: ignore[attr-defined]
    from src.core.caching.cache_layer import cached

    caching_available = True
except ImportError:
    caching_available = False
    cache_system = None

logger = logging.getLogger(__name__)
router = APIRouter(tags=["System"])

# Performance optimization: Cache health data for 5 seconds
_health_cache: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
    "data": None,
    "expires": 0,
}  # TODO(TYPE): replace Any with concrete type


@router.get(
    "/metrics",
    tags=["monitoring"],
    dependencies=[Depends(require_scopes(OAuth2Scope.ADMIN_ALL))],
)
async def prometheus_metrics(
    current_user: UserResponse = Depends(get_current_user),
) -> Response:  # TODO(TYPE): replace Any with concrete type
    try:
        from src.core.middleware.metrics_middleware import generate_metrics_response

        metrics_content = generate_metrics_response()
        return Response(content=metrics_content, media_type="text/plain")
    except Exception as metrics_error:
        logger.error(
            "Failed to generate metrics: %s: %s",
            type(metrics_error).__name__,
            metrics_error,
            exc_info=True,
        )
        return Response(content=get_metrics(), media_type="text/plain")


@router.get("/health")
async def health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """OPTIMIZED health check endpoint with caching"""
    current_time = time.time()
    if _health_cache["data"] and current_time < _health_cache["expires"]:
        return cast(
            dict[str, Any], _health_cache["data"]
        )  # TODO(TYPE): replace Any with concrete type

    try:
        settings = get_settings()
        cva_initialized = bool(app_state.get("cva_agent") is not None)
        sandbox_initialized = bool(app_state.get("sandbox_manager") is not None)
        websocket_initialized = bool(app_state.get("websocket_manager") is not None)
        database_initialized = bool(app_state.get("database_initialized", False))

        response_data = {
            "status": "healthy",
            "system": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": settings.api_version,
            "environment": settings.environment,
            "components": {
                "cva_agent": {
                    "initialized": cva_initialized,
                    "status": "active" if cva_initialized else "not_initialized",
                },
                "sandbox_manager": {
                    "initialized": sandbox_initialized,
                    "status": "active" if sandbox_initialized else "not_initialized",
                },
                "websocket_manager": {
                    "initialized": websocket_initialized,
                    "status": "active" if websocket_initialized else "not_initialized",
                },
                "database": {
                    "initialized": database_initialized,
                    "status": "active" if database_initialized else "not_initialized",
                },
            },
            "metrics": {
                "task_queue_size": len(app_state.get("task_queue", [])),
                "active_tasks": len(app_state.get("active_tasks", {})),
                "feature_flags": {
                    "docker_sandbox": get_feature_flag("real_docker_sandbox"),
                    "multi_agent": get_feature_flag("multi_agent_orchestration"),
                    "websockets": get_feature_flag("websocket_updates"),
                    "real_llm_integration": get_feature_flag("real_llm_integration"),
                },
            },
        }

        _health_cache["data"] = response_data
        _health_cache["expires"] = current_time + 5.0
        return response_data

    except Exception as e:
        logger.error("Health check error: %s: %s", type(e).__name__, e, exc_info=True)
        return {"status": "error", "error": "Internal error"}


@router.get("/status")
async def system_status_endpoint() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive system status"""
    try:
        cva_status = None
        if app_state["cva_agent"]:
            try:
                cva_status = await app_state["cva_agent"].get_status()
                cva_status = (
                    cva_status.dict() if hasattr(cva_status, "dict") else cva_status.__dict__
                )
            except Exception as e:
                logger.warning("cva_status_error: %s: %s", type(e).__name__, e, exc_info=True)
                cva_status = {"error": "Internal error", "status": "error"}

        sandbox_metrics: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        try:
            if app_state["sandbox_manager"]:
                sandbox_metrics = app_state["sandbox_manager"].get_metrics()
            else:
                sandbox_metrics = {"status": "not_initialized"}
        except Exception as e:
            logger.warning("sandbox_metrics_error: %s: %s", type(e).__name__, e, exc_info=True)
            sandbox_metrics = {"status": "error", "error": "Internal error"}

        return {
            "system": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "cva_agent": {
                    "initialized": app_state["cva_agent"] is not None,
                    "status": cva_status or {"status": "not_initialized"},
                },
                "sandbox_manager": {
                    "initialized": app_state["sandbox_manager"] is not None,
                    "active_sandboxes": (
                        len(app_state["sandbox_manager"].active_sandboxes)
                        if app_state["sandbox_manager"]
                        else 0
                    ),
                    "sandbox_type": (
                        "docker_real" if get_feature_flag("real_docker_sandbox") else "mock"
                    ),
                    "sandbox_metrics": sandbox_metrics,
                },
                "websocket_manager": {
                    "initialized": app_state["websocket_manager"] is not None,
                    "active_connections": (
                        len(app_state["websocket_manager"].active_connections)
                        if app_state["websocket_manager"]
                        else 0
                    ),
                },
                "database": {
                    "initialized": app_state.get("database_initialized", False),
                    "status": (
                        "active"
                        if app_state.get("database_initialized", False)
                        else "not_initialized"
                    ),
                },
            },
            "metrics": {
                "task_queue_size": len(app_state["task_queue"]),
                "active_tasks": len(app_state["active_tasks"]),
                "feature_flags": {
                    "docker_sandbox": get_feature_flag("real_docker_sandbox"),
                    "multi_agent": get_feature_flag("multi_agent_orchestration"),
                    "websockets": get_feature_flag("websocket_updates"),
                    "real_llm_integration": get_feature_flag("real_llm_integration"),
                },
            },
        }
    except Exception as e:
        logger.error("System status error: %s: %s", type(e).__name__, e, exc_info=True)
        # NOTE: status-endpoints retourneren altijd HTTP 200 met een status-veld in de body.
        # Bewust: monitoring-tools (UptimeRobot, Grafana) verwachten 200 voor alle status-responses;
        # een 500 zou alerts triggeren bij degraded-maar-operationele services.
        return {"system": "error", "error": "Internal error"}


@router.get("/api/status")
async def api_status_endpoint() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """API Status endpoint"""
    settings = get_settings()
    try:
        cva_initialized = app_state["cva_agent"] is not None
        sandbox_initialized = app_state["sandbox_manager"] is not None
        websocket_initialized = app_state["websocket_manager"] is not None
        database_initialized = app_state.get("database_initialized", False)

        db_status = "not_initialized"
        if database_initialized:
            try:
                import src.core.database.connection as db_conn
                db_health = db_conn.database_health_check()
                db_status = db_health.get("status", "unknown")
            except Exception as e:
                logger.warning("db_status_error: %s: %s", type(e).__name__, e, exc_info=True)
                db_status = "error: Internal error"

        return {
            "api_status": "operational",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {
                "cva_agent": {
                    "initialized": cva_initialized,
                    "status": "operational" if cva_initialized else "not_initialized",
                },
                "database": {"initialized": database_initialized, "status": db_status},
                "sandbox_manager": {
                    "initialized": sandbox_initialized,
                    "status": "operational" if sandbox_initialized else "not_initialized",
                },
                "websocket_manager": {
                    "initialized": websocket_initialized,
                    "status": "operational" if websocket_initialized else "not_initialized",
                },
            },
            "system_info": {
                "environment": settings.environment,
                "version": settings.api_version,
                "task_queue_size": len(app_state["task_queue"]),
                "active_tasks": len(app_state["active_tasks"]),
            },
        }
    except Exception as e:
        logger.error("API Status endpoint error: %s: %s", type(e).__name__, e, exc_info=True)
        # NOTE: status-endpoints retourneren altijd HTTP 200 met een status-veld in de body.
        # Bewust: monitoring-tools (UptimeRobot, Grafana) verwachten 200 voor alle status-responses;
        # een 500 zou alerts triggeren bij degraded-maar-operationele services.
        return {"api_status": "error", "error": "Internal error"}


@router.get("/cache/stats", dependencies=[Depends(require_scopes(OAuth2Scope.ADMIN_ALL))])
async def cache_statistics(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not caching_available or not cache_system:
        return {"cache_available": False, "message": "Caching system not available"}
    try:
        stats = await cache_system.get_stats()
        return {
            "cache_available": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stats": stats,
        }
    except Exception as e:
        logger.warning("cache_stats_error: %s: %s", type(e).__name__, e, exc_info=True)
        return {"cache_available": True, "error": "Internal error"}


@router.post("/cache/invalidate", dependencies=[Depends(require_scopes(OAuth2Scope.ADMIN_ALL))])
async def invalidate_cache_by_tags(
    tags: list[str] = Body(...), current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not caching_available or not cache_system:
        return {"cache_available": False, "message": "Caching system not available"}
    try:
        deleted_count = await cache_system.delete_by_tags(tags)
        return {
            "success": True,
            "deleted_count": deleted_count,
            "tags_invalidated": tags,
        }
    except Exception as e:
        logger.warning("cache_invalidate_error: %s: %s", type(e).__name__, e, exc_info=True)
        return {"success": False, "error": "Internal error"}


@router.post("/cache/clear", dependencies=[Depends(require_scopes(OAuth2Scope.ADMIN_ALL))])
async def clear_cache_namespace(
    namespace: str | None = None, current_user: UserResponse = Depends(get_current_user)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not caching_available or not cache_system:
        return {"cache_available": False, "message": "Caching system not available"}
    try:
        await cache_system.clear(namespace)
        return {"success": True, "namespace_cleared": namespace or "all"}
    except Exception as e:
        logger.warning("cache_clear_error: %s: %s", type(e).__name__, e, exc_info=True)
        return {"success": False, "error": "Internal error"}
