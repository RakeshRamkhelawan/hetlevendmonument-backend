# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Orchestration workflow endpoints: orchestrate task + route task (ADR-033 Laag 1)."""

import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.core.api.v1.orchestration.dependencies import (
    AgentRouterAgent,
    CriticAgent,
    MasterOrchestratorAgent,
    apply_governance_check,
    get_agent_router,
    get_critic_agent,
    get_master_orchestrator,
    safe_get_tenant_id,
)
from src.core.api.v1.orchestration.schemas import (
    CriticMode,
    OrchestrateTaskRequest,
    OrchestrateTaskResponse,
    RouteTaskRequest,
    RouteTaskResponse,
    TaskStatus,
    WorkflowStatusResponse,
)
from src.core.api.v1.orchestration.dependencies import limiter
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)

__all__ = [
    "workflow_router",
    "get_agent_router",
    "get_master_orchestrator",
]

workflow_router = APIRouter()


def _create_task_data(task_schema: Any) -> TaskData:  # TODO(TYPE): replace Any
    metadata: dict[str, Any] = dict(getattr(task_schema, "metadata", {}) or {})
    parameters = dict(getattr(task_schema, "parameters", {}) or {})
    if parameters:
        metadata.setdefault("parameters", parameters)
    return TaskData(
        id=str(uuid.uuid4()),
        title=task_schema.title,
        description=task_schema.description or "",
        metadata=metadata,
    )


async def _enforce_governance_or_403(
    *,
    agent_name: str,
    task_action: str,
    task_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    agent_department: str = "workflow",
    agent_specialisation: str = "orchestration",
    agent_capabilities: list[str] | None = None,
) -> None:
    allowed, reason = await apply_governance_check(
        agent_name=agent_name,
        task_action=task_action,
        agent_department=agent_department,
        agent_specialisation=agent_specialisation,
        agent_capabilities=agent_capabilities or [],
        task_params=task_params,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"GOVERNANCE_BLOCK: {reason or 'blocked by policy'}",
        )


@workflow_router.post("/task", response_model=OrchestrateTaskResponse)
@limiter.limit("10/minute")
async def orchestrate_task(
    request: Request,
    response: Response,
    task_request: OrchestrateTaskRequest,
    orchestrator: MasterOrchestratorAgent = Depends(get_master_orchestrator),
    critic: CriticAgent = Depends(get_critic_agent),
    tenant_id: int = Depends(safe_get_tenant_id),
) -> OrchestrateTaskResponse:
    """Orchestrate a complex task through the MasterOrchestratorAgent."""
    start_time = time.time()
    try:
        task_data = _create_task_data(task_request.task)
        task_data.parameters["workflow_mode"] = task_request.workflow_mode.value
        task_data.parameters["max_subtasks"] = task_request.max_subtasks

        await _enforce_governance_or_403(
            agent_name="MasterOrchestratorAgent",
            task_action="orchestrate_task",
            task_params={
                "tenant_id": tenant_id,
                "title": task_request.task.title,
                "workflow_mode": task_request.workflow_mode.value,
                "max_subtasks": task_request.max_subtasks,
            },
            agent_capabilities=["orchestration", "planning"],
        )

        result = await orchestrator.process_task(task_data)
        result_data: dict[str, Any] = (  # TODO(TYPE): replace Any with concrete type
            result.result_data or {}
        )  # TODO(TYPE): replace Any with concrete type
        workflow_id = result_data.get("workflow_id", task_data.id)

        task_response = OrchestrateTaskResponse(
            workflow_id=workflow_id,
            status=TaskStatus.COMPLETED if result.success else TaskStatus.FAILED,
            synthesis=result_data.get("synthesis"),
            total_execution_time=time.time() - start_time,
        )

        if task_request.require_critic_review and result.success:
            critique = await critic.critique_task(
                agent_name="MasterOrchestratorAgent",
                task_id=workflow_id,
                result=result,
                mode=CriticMode.ADVISORY.value,
            )
            task_response.critique = {
                "score": critique.score,
                "issues": [str(i) for i in critique.issues],
                "suggestions": critique.suggestions,
            }

        return task_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Orchestration failed for tenant %s: %s: %s",
            tenant_id,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Orchestration failed",
        )


@workflow_router.get("/task/{workflow_id}", response_model=WorkflowStatusResponse)
@limiter.limit("60/minute")
async def get_workflow_status(
    request: Request,
    response: Response,
    workflow_id: str,
    orchestrator: MasterOrchestratorAgent = Depends(get_master_orchestrator),
) -> WorkflowStatusResponse:
    """Get status of a specific workflow."""
    plan = orchestrator.get_workflow_plan(workflow_id)

    if plan is not None:
        sub_tasks = getattr(plan, "sub_tasks", getattr(plan, "subtasks", []))
        total = len(sub_tasks)
        completed = sum(1 for st in sub_tasks if getattr(st, "status", "") == "completed")
        failed = sum(1 for st in sub_tasks if getattr(st, "status", "") == "failed")
        plan_status = getattr(plan, "status", TaskStatus.PENDING)
        status_key = plan_status.value if hasattr(plan_status, "value") else str(plan_status)
        status_map = {
            "pending": TaskStatus.PENDING,
            "running": TaskStatus.RUNNING,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
        }
        return WorkflowStatusResponse(
            workflow_id=workflow_id,
            exists=True,
            status=status_map.get(status_key, TaskStatus.PENDING),
            subtask_count=total,
            completed_subtasks=completed,
            failed_subtasks=failed,
            progress_percentage=(completed / total * 100) if total > 0 else 0.0,
        )

    return WorkflowStatusResponse(workflow_id=workflow_id, exists=False)


@workflow_router.post("/route", response_model=RouteTaskResponse)
@limiter.limit("30/minute")
async def route_task(
    request: Request,
    response: Response,
    task_request: RouteTaskRequest,
    agent_router: AgentRouterAgent = Depends(get_agent_router),
    tenant_id: int = Depends(safe_get_tenant_id),
) -> RouteTaskResponse:
    """Route a task to the most appropriate agent."""
    task_id = str(uuid.uuid4())
    try:
        await _enforce_governance_or_403(
            agent_name="AgentRouterAgent",
            task_action="route_task",
            task_params={
                "tenant_id": tenant_id,
                "title": task_request.task.title,
                "required_capabilities": task_request.required_capabilities,
                "preferred_agents": task_request.preferred_agents,
                "fallback_to_llm": task_request.fallback_to_llm,
            },
            agent_capabilities=["routing", "capability_matching"],
        )

        task_metadata = {
            **task_request.task.metadata,
            **task_request.task.parameters,
            "required_capabilities": task_request.required_capabilities,
            "preferred_agents": task_request.preferred_agents,
            "fallback_to_llm": task_request.fallback_to_llm,
        }
        task_data = TaskData(
            id=task_id,
            title=task_request.task.title,
            description=task_request.task.description or "",
            metadata=task_metadata,
        )

        agent_id = await agent_router.route(task_data)
        manifest = agent_router.get_manifest(agent_id)
        agent_type = manifest.agent_type if manifest else None

        routing_method = "fallback"
        cache_hit = False
        confidence = 0.5

        cached = agent_router.cache_lookup(
            task_request.task.title, task_request.required_capabilities
        )
        if cached and cached.agent_id == agent_id:
            routing_method = "cache"
            cache_hit = True
            confidence = 0.95

        if routing_method == "fallback" and task_request.required_capabilities:
            matched_agent = agent_router.capability_match(task_request.required_capabilities)
            if matched_agent == agent_id:
                routing_method = "capability_match"
                confidence = 0.85

        return RouteTaskResponse(
            task_id=task_id,
            routed_to_agent=agent_id,
            agent_type=agent_type,
            routing_method=routing_method,
            confidence_score=confidence,
            cache_hit=cache_hit,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Routing failed for tenant %s: %s: %s", tenant_id, type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task routing failed",
        ) from e
