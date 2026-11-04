"""FastAPI main application with compatibility exports for legacy tests."""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, cast, Optional
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from starlette.requests import Request

from src.core.agents.cva_orchestrator import create_ultimate_cva_agent
from src.core.api.chat_endpoints import _build_conversation_context
from src.core.api.setup.app_state import app_state
from src.core.api.setup.exception_handlers import setup_exception_handlers
from src.core.api.setup.middleware_config import setup_middleware
import os as _os

_TESTING = _os.environ.get("TESTING") == "1" or "PYTEST_CURRENT_TEST" in _os.environ

if not _TESTING:
    from src.core.api.setup.router_registry import (  # NOTE: optional routers may be None when imports fail
        metrics_middleware_available,
        register_routers,
        security_available,
    )
else:
    # Stubs so module-level code that references these names doesn't crash in tests
    metrics_middleware_available = False
    security_available = False

    def register_routers(app: "FastAPI") -> None:
        pass


from src.core.api.websocket_manager import WebSocketManager
from src.core.auth.api_deps import get_current_user
from src.core.database.database import initialize_database
from src.core.sandbox.sandbox_manager import SandboxManagerFactory
from src.core.shared.config import get_feature_flag, get_settings
from src.core.shared.interfaces import SandboxEnvironment, TaskData
from src.core.shared.production_logging import log_startup_validation, production_logger
from src.core.types import IsolationLevel

# Setup logging
logger = logging.getLogger(__name__)

_get_cache: Any = None
try:
    from src.core.caching.cache_layer import get_cache as _get_cache

    caching_available = True
except ImportError:
    caching_available = False


@asynccontextmanager
async def lifespan(
    app_instance: FastAPI,
) -> AsyncIterator[None]:
    startup_success: Any = log_startup_validation()  # TODO(TYPE): replace Any with concrete type
    if inspect.isawaitable(startup_success):
        startup_success = await startup_success

    if not startup_success:
        raise RuntimeError("Critical configuration missing - startup blocked")

    app_state["database_initialized"] = False
    app_state["websocket_manager"] = None
    app_state["cva_agent"] = None
    app_state["sandbox_manager"] = None

    try:
        db_initialized: Any = initialize_database()  # TODO(TYPE): replace Any with concrete type
        if inspect.isawaitable(db_initialized):
            db_initialized = await db_initialized
        app_state["database_initialized"] = bool(db_initialized)
    except Exception:
        app_state["database_initialized"] = False

    app_state["websocket_manager"] = WebSocketManager()

    cva_agent: Any = create_ultimate_cva_agent()  # TODO(TYPE): replace Any with concrete type
    if inspect.isawaitable(cva_agent):
        cva_agent = await cva_agent
    app_state["cva_agent"] = cva_agent

    sandbox_manager: object = (
        SandboxManagerFactory.create_manager()
    )  # TODO(TYPE): replace Any with concrete type
    if inspect.isawaitable(sandbox_manager):
        sandbox_manager = await sandbox_manager
    app_state["sandbox_manager"] = sandbox_manager

    # Wire agent_runtime facade (ADR-034)
    try:
        from src.core.agents.api import register_agent_runtime
        from src.core.agents.master_orchestrator_agent import get_master_orchestrator
        from src.core.agents.runtime_adapter import MasterOrchestratorRuntimeAdapter
        from src.core.database.redis import get_redis_client
        from src.core.database.session import get_db_session

        # NOTE: tenant_id=1 is the system-level bootstrap instance; per-tenant routing
        # is handled by task.tenant_id at call time, not at registration time.
        # async_session_factory + redis_client wired so _get_router() reaches
        # DB-backed agent-discovery (SP-ADR023-002 Dag 1, FA-NEW-001) and the
        # cross-worker routing cache (Dag 2) -- without them this bootstrap path
        # would permanently lock tenant_id=1's AgentRouterAgent singleton without
        # discovery/cache.
        redis_client = await get_redis_client()
        orchestrator = get_master_orchestrator(
            tenant_id=1, async_session_factory=get_db_session, redis_client=redis_client
        )
        init_ok = await orchestrator.initialize()
        if not init_ok:
            logger.warning(
                "agent_runtime: MasterOrchestratorAgent LLM init failed; "
                "facade NOT registered -- agent_runtime will raise RuntimeError on use"
            )
        else:
            register_agent_runtime(MasterOrchestratorRuntimeAdapter(orchestrator))
            logger.info("agent_runtime facade wired: MasterOrchestratorRuntimeAdapter")
    except Exception as wire_exc:
        logger.error(
            "agent_runtime facade wiring failed: %s: %s",
            type(wire_exc).__name__,
            wire_exc,
            exc_info=True,
        )
        # Non-fatal: facade raises RuntimeError on use, not at startup

    try:
        yield
    finally:
        pass


# Create FastAPI app
settings = get_settings()
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="AI Multi-Agent System API for Sanskriti Setu (Modular)",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
    # openapi_url stond hier NIET, dus gold de FastAPI-default en werd het schema
    # onvoorwaardelijk geserveerd terwijl de twee viewers wel dicht gingen. `/openapi.json` is
    # de payload; `/docs` en `/redoc` zijn alleen viewers (ADR-036 OP-124).
    openapi_url="/openapi.json" if settings.debug else None,
)

# Configure Components (Refactored)
setup_middleware(app, security_available, metrics_middleware_available)
setup_exception_handlers(app)
register_routers(app)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception in compatibility handler: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "message": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def _status_value(value: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    return cast(
        dict[str, Any], getattr(value, "value", value)
    )  # TODO(TYPE): replace Any with concrete type


async def _get_sandbox_metrics() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    sandbox_manager: Any = app_state[
        "sandbox_manager"
    ]  # TODO(TYPE): replace Any with concrete type
    if sandbox_manager is None:
        return {}

    try:
        sandbox_metrics: dict[
            str, Any  # TODO(TYPE): replace Any with concrete type
        ] = (  # TODO(TYPE): needs SandboxMetrics TypedDict  # TODO(TYPE): replace Any with concrete type
            getattr(sandbox_manager, "sandbox_metrics", {}) or {}
        )
        active_sandboxes: list[Any] = (  # TODO(TYPE): replace Any with concrete type
            getattr(sandbox_manager, "active_sandboxes", []) or []
        )  # TODO(TYPE): replace Any with concrete type

        total_executions: int = sum(
            metric.get("executions_count", 0) for metric in sandbox_metrics.values()
        )
        successful_executions: int = sum(
            metric.get("successful_executions", 0) for metric in sandbox_metrics.values()
        )
        failed_executions: int = sum(
            metric.get("failed_executions", 0) for metric in sandbox_metrics.values()
        )
        total_execution_time: float = sum(
            metric.get("total_execution_time", 0.0) for metric in sandbox_metrics.values()
        )

        return {
            "total_sandboxes_created": len(sandbox_metrics),
            "active_sandboxes": len(active_sandboxes),
            "total_executions": total_executions,
            "successful_executions": successful_executions,
            "failed_executions": failed_executions,
            "success_rate": (
                round((successful_executions / total_executions) * 100, 2)
                if total_executions
                else 0
            ),
            "avg_execution_time": (
                round(total_execution_time / total_executions, 2) if total_executions else 0
            ),
            "docker_available": getattr(sandbox_manager, "_docker_client", None) is not None,
        }
    except Exception as exc:
        logger.error("Sandbox metrics collection failed: %s", exc)
        return {"error": "Er is een interne fout opgetreden."}


async def chat_with_cva(
    message: dict[str, object],
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    agent: Any = app_state["cva_agent"]  # TODO(TYPE): replace Any with concrete type
    if not agent:
        raise HTTPException(status_code=503, detail="CVA agent not initialized")

    try:
        current_message: str = str(message.get("message", ""))
        conversation_history: Any = message.get(  # TODO(TYPE): replace Any with concrete type
            "conversation_history", []
        )  # TODO(TYPE): replace Any with concrete type
        user_id: Any = message.get(
            "user_id", "anonymous"
        )  # TODO(TYPE): replace Any with concrete type
        llm_provider: Any = message.get(
            "llm_provider", "ollama"
        )  # TODO(TYPE): replace Any with concrete type

        task: TaskData = TaskData(
            title="CVA Chat",
            description=current_message,
            metadata={
                "type": "general",
                "source": "chat_interface",
                "user_id": user_id,
                "conversation_history": conversation_history,
                "conversation_context": _build_conversation_context(conversation_history),
                "llm_provider": llm_provider,
            },
        )

        result: Any = await agent.process_task(task)  # TODO(TYPE): replace Any with concrete type
        websocket_manager = cast(Optional[WebSocketManager], app_state.get("websocket_manager"))
        if get_feature_flag("websocket_updates") and websocket_manager:
            await websocket_manager.broadcast(
                {
                    "type": "cva_response",
                    "task_id": task.id,
                    "result": result.dict() if hasattr(result, "dict") else result.__dict__,
                }
            )

        return {
            "task_id": task.id,
            "success": result.success,
            "response": result.result_data,
            "execution_time": result.execution_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "conversation_id": None,
            "persistent": False,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("CVA chat error: %s", exc)
        raise HTTPException(status_code=500, detail="CVA processing failed")


async def request_strategy(
    request: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ],  # TODO(TYPE): JSON request body -- needs Pydantic model  # TODO(TYPE): replace Any with concrete type
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    agent: Any = app_state["cva_agent"]  # TODO(TYPE): replace Any with concrete type
    if not agent:
        raise HTTPException(status_code=503, detail="CVA agent not initialized")

    task: TaskData = TaskData(
        title="Strategic Analysis",
        description=request.get("description", ""),
        metadata={
            "type": "strategic_planning",
            "context": request.get("context", {}),
            "objectives": request.get("objectives", []),
        },
    )
    result: Any = await agent.process_task(task)  # TODO(TYPE): replace Any with concrete type
    return {
        "task_id": task.id,
        "strategy": result.result_data,
        "success": result.success,
        "execution_time": result.execution_time,
    }


async def create_task(
    task_request: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ],  # TODO(TYPE): JSON request body -- needs Pydantic model  # TODO(TYPE): replace Any with concrete type
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, str]:
    try:
        task: TaskData = TaskData(
            title=task_request.get("title", "Untitled Task"),
            description=task_request.get("description", ""),
            priority=task_request.get("priority", "MEDIUM"),
            metadata=task_request.get("metadata", {}),
        )
        task_queue: Any = app_state["task_queue"]  # TODO(TYPE): replace Any with concrete type
        task_queue.append(task)

        websocket_manager = cast(Optional[WebSocketManager], app_state.get("websocket_manager"))
        if get_feature_flag("websocket_updates") and websocket_manager:
            await websocket_manager.broadcast(
                {
                    "type": "task_created",
                    "task": task.dict() if hasattr(task, "dict") else task.__dict__,
                }
            )

        return {
            "task_id": task.id,
            "status": "created",
            "message": "Task created successfully",
        }
    except Exception as exc:
        logger.error("Task creation error: %s", exc)
        raise HTTPException(status_code=500, detail="Task creation failed")


async def list_tasks(
    status: str | None = None,
    limit: int = 50,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    try:
        tasks: list[Any] = list(
            app_state["task_queue"]
        )  # TODO(TYPE): replace Any with concrete type
        if status:
            tasks = [task for task in tasks if _status_value(task.status) == status]  # type: ignore[comparison-overlap]
        tasks = tasks[:limit]
        return [
            {
                "id": task.id,
                "title": task.title,
                "status": _status_value(task.status),
                "priority": _status_value(task.priority),
                "created_at": task.created_at.isoformat(),
            }
            for task in tasks
        ]
    except Exception as exc:
        logger.error("Task listing error: %s", exc)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


async def execute_task(
    task_id: str,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    active_tasks: Any = app_state["active_tasks"]  # TODO(TYPE): replace Any with concrete type
    try:
        task_queue: Any = app_state["task_queue"]  # TODO(TYPE): replace Any with concrete type
        task: Any = next(
            (item for item in task_queue if item.id == task_id), None
        )  # TODO(TYPE): replace Any with concrete type
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        agent: Any = app_state["cva_agent"]  # TODO(TYPE): replace Any with concrete type
        if not agent:
            raise HTTPException(status_code=503, detail="No agents available")

        active_tasks[task_id] = task
        result: Any = await agent.process_task(task)  # TODO(TYPE): replace Any with concrete type
        task.status = "completed" if result.success else "failed"
        active_tasks.pop(task_id, None)
        return {
            "task_id": task_id,
            "success": result.success,
            "result": result.result_data,
            "execution_time": result.execution_time,
        }
    except Exception as exc:
        active_tasks.pop(task_id, None)
        logger.error("Task execution error: %s", exc)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


async def get_llm_metrics(
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    agent: Any = app_state["cva_agent"]  # TODO(TYPE): replace Any with concrete type
    if not agent:
        raise HTTPException(status_code=503, detail="CVA agent not initialized")

    try:
        if not hasattr(agent, "get_cva_metrics"):
            raise AttributeError("CVA agent missing get_cva_metrics method")

        raw_metrics: Any = agent.get_cva_metrics()  # TODO(TYPE): replace Any with concrete type
        return {
            "metrics": {
                "providers": {
                    "anthropic": {"status": "available"},
                    "google": {"status": "available"},
                },
                "current_provider": "anthropic",
                "total_requests": raw_metrics.get("tasks_processed", 0),
                "average_execution_time": raw_metrics.get("average_execution_time", 0),
                "raw": raw_metrics,
            }
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Request failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


async def create_sandbox(
    config: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ],  # TODO(TYPE): JSON request body -- needs Pydantic model  # TODO(TYPE): replace Any with concrete type
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    sandbox_manager: Any = app_state[
        "sandbox_manager"
    ]  # TODO(TYPE): replace Any with concrete type
    if not sandbox_manager:
        raise HTTPException(status_code=503, detail="Sandbox manager not initialized")

    try:
        sandbox_config: SandboxEnvironment = SandboxEnvironment(
            isolation_level=IsolationLevel(config.get("isolation_level", "mock")),
            resource_limits=config.get("resource_limits", {}),
            network_access=config.get("network_access", False),
            filesystem_access=config.get("filesystem_access", {}),
        )
        sandbox_id: str = await sandbox_manager.create_sandbox(sandbox_config)
        return {
            "sandbox_id": sandbox_id,
            "status": "created",
            "isolation_level": str(sandbox_config.isolation_level.value),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Sandbox creation error: %s", exc)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


async def get_sandbox_status(
    sandbox_id: str,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    sandbox_manager: Any = app_state[
        "sandbox_manager"
    ]  # TODO(TYPE): replace Any with concrete type
    if not sandbox_manager:
        raise HTTPException(status_code=503, detail="Sandbox manager not initialized")

    try:
        return cast(
            dict[str, Any],  # TODO(TYPE): replace Any with concrete type
            await sandbox_manager.get_sandbox_status(
                sandbox_id
            ),  # TODO(TYPE): replace Any with concrete type
        )  # TODO(TYPE): replace Any with concrete type
    except Exception as exc:
        logger.error("Sandbox status error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to get sandbox status")


@app.get("/")
async def root() -> dict[str, str]:
    """Root redirect to docs"""
    return {"message": "Sanskriti Setu API is operational", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.core.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )


# ---------------------------------------------------------------------------
# ADR-033 compatibility exports for legacy tests
# ---------------------------------------------------------------------------
# These aliases allow pre-ADR-033 tests to import routers from main.py.
# New code should import from src.core.api.v1.<domain> directly.

try:
    from src.core.api.v1.security.auth_router import auth_router  # noqa: F401
except Exception:
    auth_router = None  # type: ignore[assignment]

try:
    from src.core.api.v1.admin import domain_router as admin_router  # noqa: F401
except Exception:
    admin_router = None  # type: ignore[assignment]

try:
    from src.core.api.v1.security.management_router import management_router  # noqa: F401
except Exception:
    management_router = None  # type: ignore[assignment]

try:
    from src.core.api.sentiment_scanner_endpoints import router as sentiment_router  # type: ignore[attr-defined]  # noqa: F401
except Exception:
    sentiment_router = None  # type: ignore[assignment]
