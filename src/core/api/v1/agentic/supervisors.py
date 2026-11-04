"""Supervisor management API endpoints."""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

import logging
from typing import Any, Dict, List, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.core.api.v1.agentic.dependencies import FinanceSupervisor, SupervisorID, TaskStatus
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.exceptions import AuthError
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supervisors", tags=["Supervisors"])


# Models
class SupervisorInfo(BaseModel):
    id: str
    domain: str
    managed_agents_count: int
    status: str


class SupervisorDetail(BaseModel):
    id: str
    domain: str
    managed_agents: list[str]
    capabilities: list[str]


class TaskExecuteRequest(BaseModel):
    task_type: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class TaskExecuteResponse(BaseModel):
    supervisor_id: str
    status: str
    subtasks: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    results: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    execution_time_ms: int


class AgentStatusResponse(BaseModel):
    agent_id: str
    status: str
    last_executed: str | None
    success_rate: float


# Endpoints
@router.get("", response_model=list[SupervisorInfo])
async def list_supervisors() -> list[SupervisorInfo]:
    """List all available supervisors."""
    # In production, this would query from a registry
    supervisors = [
        SupervisorInfo(
            id=SupervisorID.FINANCE,
            domain="Finance & Treasury",
            managed_agents_count=5,
            status="active",
        ),
        SupervisorInfo(
            id=SupervisorID.HR, domain="HR & Culture", managed_agents_count=4, status="active"
        ),
        SupervisorInfo(
            id=SupervisorID.IT, domain="IT & Security", managed_agents_count=4, status="active"
        ),
        SupervisorInfo(
            id=SupervisorID.LEGAL,
            domain="Legal & Compliance",
            managed_agents_count=4,
            status="active",
        ),
    ]
    return supervisors


@router.get("/{supervisor_id}", response_model=SupervisorDetail)
async def get_supervisor(supervisor_id: str) -> SupervisorDetail:
    """Get detailed information about a specific supervisor."""
    # Map supervisor IDs to their details
    supervisor_map: dict[SupervisorID, SupervisorDetail] = {
        SupervisorID.FINANCE: SupervisorDetail(
            id=SupervisorID.FINANCE,
            domain="Finance & Treasury",
            managed_agents=[
                "finance.tax_compliance.001",
                "finance.audit_compliance.001",
                "finance.ar_ap.001",
                "finance.forecasting.001",
                "finance.investment.001",
            ],
            capabilities=[
                "tax_calculation",
                "audit_review",
                "invoice_processing",
                "budget_forecast",
                "investment_analysis",
            ],
        ),
        SupervisorID.HR: SupervisorDetail(
            id=SupervisorID.HR,
            domain="HR & Culture",
            managed_agents=[
                "hr.talent_acquisition.001",
                "hr.employee_onboarding.001",
                "hr.payroll.001",
                "hr.sentiment_analysis.001",
            ],
            capabilities=[
                "talent_acquisition",
                "employee_onboarding",
                "payroll_processing",
                "sentiment_analysis",
            ],
        ),
    }

    # Convert string to enum for lookup
    try:
        supervisor_enum = SupervisorID(supervisor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    if supervisor_enum not in supervisor_map:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    return supervisor_map[supervisor_enum]


@router.post("/{supervisor_id}/execute", response_model=TaskExecuteResponse)
async def execute_supervisor_task(
    supervisor_id: str,
    request: TaskExecuteRequest,
    current_user: UserResponse = Depends(get_current_user),
) -> TaskExecuteResponse:
    """Execute a task through a specific supervisor."""
    import time

    start_time = time.time()

    # Get the appropriate supervisor
    if supervisor_id == SupervisorID.FINANCE:
        supervisor = FinanceSupervisor(
            agent_id="finance.supervisor.temp",
            tenant_id=current_user.tenant_id,
        )
    else:
        raise HTTPException(
            status_code=400, detail=f"Supervisor {supervisor_id} execution not yet implemented"
        )

    try:
        # Prepare task as TaskData model
        task = TaskData(
            title=request.task_type,
            description=f"Task of type {request.task_type}",
            metadata={
                "type": request.task_type,
                **request.parameters,
                "tenant_id": current_user.tenant_id,
            },
        )

        # Decompose task into subtasks
        subtasks = await supervisor.decompose_task(task)

        # Execute subtasks (select agents and execute)
        agent_ids = await supervisor.select_agents(subtasks)

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Convert subtasks to dicts for response
        subtasks_dict: list[dict[str, Any]] = [  # TODO(TYPE): replace Any with concrete type
            {"id": st.id, "title": st.title, "description": st.description} for st in subtasks
        ]

        return TaskExecuteResponse(
            supervisor_id=supervisor_id,
            status="completed" if agent_ids else "no_agents",
            subtasks=subtasks_dict,
            results=[{"agents_selected": agent_ids}],
            execution_time_ms=execution_time_ms,
        )

    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error("supervisor operation failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/{supervisor_id}/agents")
async def list_supervisor_agents(supervisor_id: str) -> list[AgentStatusResponse]:
    """List all agents managed by a supervisor with their status."""
    # Placeholder - would query from database
    agents = [
        AgentStatusResponse(
            agent_id=f"{supervisor_id}.agent_001",
            status="active",
            last_executed="2026-02-28T10:00:00Z",
            success_rate=0.95,
        ),
        AgentStatusResponse(
            agent_id=f"{supervisor_id}.agent_002",
            status="active",
            last_executed="2026-02-28T09:30:00Z",
            success_rate=0.92,
        ),
    ]
    return agents


@router.get("/{supervisor_id}/agents/{agent_id}/status")
async def get_agent_status(supervisor_id: str, agent_id: str) -> AgentStatusResponse:
    """Get detailed status of a specific agent."""
    # Placeholder
    return AgentStatusResponse(
        agent_id=agent_id, status="active", last_executed="2026-02-28T10:00:00Z", success_rate=0.95
    )


@router.post("/{supervisor_id}/agents/{agent_id}/execute")
async def execute_agent_directly(
    supervisor_id: str, agent_id: str, request: TaskExecuteRequest
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a task directly on a specific agent."""
    # Placeholder - would route to specific agent
    return {
        "agent_id": agent_id,
        "supervisor_id": supervisor_id,
        "status": "success",
        "result": {"message": f"Agent {agent_id} executed successfully"},
        "execution_time_ms": 150,
    }
