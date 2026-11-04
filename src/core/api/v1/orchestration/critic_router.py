# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Orchestration critic endpoint (ADR-033 Laag 1)."""

import logging
import time
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from src.core.api.v1.orchestration.dependencies import (
    CriticAgent,
    CritiqueStore,
    apply_governance_check,
    consent_read_limit,
    get_critic_agent,
    get_critique_store,
)
from src.core.api.v1.orchestration.schemas import (
    CritiqueIssueSchema,
    CritiqueRequest,
    CritiqueResponseSchema,
    TelemetryDataPoint,
    TelemetryResponse,
)

logger = logging.getLogger(__name__)

critic_router = APIRouter()


@critic_router.get("/critic-health")
@consent_read_limit
async def get_critic_health(
    request: Request,
    critic: CriticAgent = Depends(get_critic_agent),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get system health based on critique statistics."""
    result = await critic.get_system_health()
    return {"success": True, "data": result}


@critic_router.get("/telemetry", response_model=TelemetryResponse)
@consent_read_limit
async def get_critic_telemetry(
    request: Request,
    hours: int = Query(default=24, ge=1, le=168),
    critic: CriticAgent = Depends(get_critic_agent),
    store: CritiqueStore = Depends(get_critique_store),
) -> TelemetryResponse:
    """Get hourly critique telemetry for the current tenant (last N hours)."""
    stats = await store.get_timeseries_stats(tenant_id=critic.tenant_id, hours=hours)
    return TelemetryResponse(
        success=True,
        data=[TelemetryDataPoint(**row) for row in stats],
    )


@critic_router.get("/{agent_name}/report")
@consent_read_limit
async def get_agent_report(
    request: Request,
    agent_name: str = Path(..., max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$"),
    critic: CriticAgent = Depends(get_critic_agent),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get critique report for a specific agent."""
    result = await critic.get_agent_report(agent_name)
    return {"success": True, "data": result}


@critic_router.get("/{agent_name}/common-issues")
@consent_read_limit
async def get_common_issues(
    request: Request,
    agent_name: str = Path(..., max_length=100, pattern=r"^[a-zA-Z0-9_\-]+$"),
    critic: CriticAgent = Depends(get_critic_agent),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get most common issues for a specific agent."""
    result = await critic.get_common_issues(agent_name)
    return {"success": True, "data": result}


@critic_router.post("/critique", response_model=CritiqueResponseSchema)
async def critique_output(
    request: CritiqueRequest,
    critic: CriticAgent = Depends(get_critic_agent),
) -> CritiqueResponseSchema:
    """Critique agent output quality."""
    from src.core.shared.interfaces import ExecutionResult

    tenant_id = critic.tenant_id
    start_time = time.time()

    allowed, reason = await apply_governance_check(
        agent_name="CriticAgent",
        task_action="critique_output",
        agent_department="workflow",
        agent_specialisation="orchestration",
        agent_capabilities=["quality_control", "critique"],
        task_params={
            "tenant_id": tenant_id,
            "agent_name": request.agent_name,
            "task_id": request.task_id,
            "mode": request.mode.value,
        },
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"GOVERNANCE_BLOCK: {reason or 'blocked by policy'}",
        )

    result = ExecutionResult(
        task_id=request.task_id,
        success=request.error is None,
        result_data=request.output,
        execution_time=request.latency_ms / 1000.0 if request.latency_ms else 0,
        error_message=request.error,
    )

    critique_result = await critic.critique_task(
        agent_name=request.agent_name,
        task_id=request.task_id,
        result=result,
        mode=request.mode.value,
    )

    processing_time = int((time.time() - start_time) * 1000)

    issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for issue in critique_result.issues:
        to_dict = getattr(issue, "to_dict", None)
        if callable(to_dict):
            issue_dict = cast(
                dict[str, Any], to_dict()  # TODO(TYPE): replace Any with concrete type
            )  # TODO(TYPE): replace Any with concrete type
            issues.append(
                CritiqueIssueSchema(
                    severity=issue_dict.get("severity", "warning"),
                    message=issue_dict.get("message", str(issue)),
                    category=issue_dict.get("category", "general"),
                )
            )
        else:
            issues.append(
                CritiqueIssueSchema(
                    severity="warning",
                    message=str(issue),
                    category="general",
                )
            )

    return CritiqueResponseSchema(
        task_id=request.task_id,
        agent_name=request.agent_name,
        score=critique_result.score,
        issues=issues,
        suggestions=critique_result.suggestions,
        approved=critique_result.score >= 0.6,
        should_retry=critique_result.score < 0.4,
        processing_time_ms=processing_time,
    )
