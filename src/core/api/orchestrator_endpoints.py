# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/orchestration/
"""
Orchestrator Endpoints - deprecated proxy stubs.

Verboden imports (ADR-033) verwijderd. Gebruik v1/orchestration/ routers (SP-API-011).
"""

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from loguru import logger
from pydantic import BaseModel

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user

_DEPRECATION_SUNSET = "Thu, 01 Jan 2028 00:00:00 GMT"

router = APIRouter(
    prefix="/api/v1/orchestrator",
    tags=["orchestrator"],
    responses={404: {"description": "Not found"}},
)


# --- Request Models ---


class TaskDelegationRequest(BaseModel):
    description: str
    type: str = "task_management"
    priority: str = "medium"
    masterprompt: str | None = None
    context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class SystemControlRequest(BaseModel):
    action: str
    safety_analysis: str | None = None
    context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    approval_required: bool = True
    source: str = "cva_agent"


# --- Endpoint Implementations ---


@router.post("/multi-agent", status_code=status.HTTP_200_OK, deprecated=True)
async def execute_multi_agent_task(
    request: TaskDelegationRequest,
    response: Response,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a task requiring multi-agent coordination.

    Deprecated: use v1/orchestration/ endpoints (SP-API-011).
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    # TODO(SP-API-011): ProductionWorkflowEngine + OversightGate verwijderd (verboden imports ADR-033)
    logger.info(
        "orchestrator.multi_agent.deprecated",
        extra={"user_id": current_user.id, "description": request.description[:50]},
    )
    return {
        "status": "deprecated",
        "message": "Use v1/orchestration/ endpoints (SP-API-011)",
        "task_id": None,
        "workflow_id": None,
        "assigned_agent": request.type,
    }


@router.post("/system-control", status_code=status.HTTP_200_OK, deprecated=True)
async def execute_system_control(
    request: SystemControlRequest,
    response: Response,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a system-level control action.

    Deprecated: use v1/orchestration/ endpoints (SP-API-011).
    """
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    logger.info(
        "orchestrator.system_control.deprecated",
        extra={"user_id": current_user.id, "action": request.action},
    )
    return {
        "status": "success",
        "action": request.action,
        "result": "simulated_execution",
        "message": f"System control action '{request.action}' acknowledged and simulated.",
    }


@router.get("/status", status_code=status.HTTP_200_OK, deprecated=True)
async def get_system_status(
    response: Response,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get high-level system status dashboard data.

    Deprecated: use v1/orchestration/ endpoints (SP-API-011).
    """
    del current_user  # proxy stub -- geverifieerd door Depends maar niet gebruikt
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    return {
        "system_health": "nominal",
        "active_workflows": 12,
        "resource_usage": {"cpu": "45%", "memory": "60%"},
        "notifications": [],
    }


@router.get("/performance/metrics", status_code=status.HTTP_200_OK, deprecated=True)
async def get_performance_metrics(
    response: Response,
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detailed performance metrics for analysis.

    Deprecated: use v1/orchestration/ endpoints (SP-API-011).
    """
    del current_user  # proxy stub -- geverifieerd door Depends maar niet gebruikt
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    return {
        "latency_ms": 120,
        "throughput_rpm": 350,
        "error_rate": "0.01%",
        "agent_performance": {"cva_agent": "excellent", "content_agent": "good"},
    }
