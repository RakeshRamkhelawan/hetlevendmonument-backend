# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow execution core sub-router (SP-API-003 Dag 2).

Routes:
    POST /api/v1/workflows/{workflow_id}/execute
    GET  /api/v1/workflows/executions/{execution_id}
    GET  /api/v1/workflows/executions
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Protocol, TypeAlias, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.api.v1.workflow.dependencies import get_db, OAuth2Scope
from src.core.auth.api_deps import require_scopes as _require_scopes
from src.core.exceptions import raise_not_found, raise_validation_error
from src.core.middleware.tenant_context import get_current_tenant_id as _get_current_tenant_id
from .dependencies import (
    C7ExecutionTask as ExecutionTask,
    C7Workflow as Workflow,
    C7WorkflowExecution as WorkflowExecution,
    WorkflowStatus,
    stap_overzicht,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows-c7"])


ExecutionResponse: TypeAlias = dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class WorkflowExecuteRequest(BaseModel):
    """Request to start a workflow execution."""

    input_data: dict[str, Any] = Field(default_factory=dict, description="Input data for workflow")
    version: int | None = Field(None, description="Workflow version (defaults to latest)")


class ExecutionStatusResponse(BaseModel):
    """Response with execution status."""

    execution_id: str
    workflow_id: str
    status: str
    input_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    output_data: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    start_time: str | None
    end_time: str | None
    duration: float | None
    tasks_completed: int
    tasks_failed: int
    tasks_total: int
    error_message: str | None
    stappen: list[dict[str, str | None]] = Field(
        default_factory=list,
        description="Per stap: naam, Nederlandse status, uitkomst en reden van een weigering",
    )


class ExecutionListItem(BaseModel):
    """Execution list item."""

    execution_id: str
    workflow_id: str
    status: str
    start_time: str | None
    end_time: str | None
    duration: float | None


def _dt(dt: datetime | None) -> str | None:
    """Serialize datetime to ISO format."""
    return dt.isoformat() if dt else None


async def get_tenant() -> int:
    """Get tenant ID with error handling."""
    tenant_id = _get_current_tenant_id()
    if not tenant_id:
        raise_validation_error(
            "Tenant context required. Ensure you are authenticated with a valid JWT token containing tenant_id.",
            {"error": "MISSING_TENANT_CONTEXT"},
        )
    return tenant_id


@router.post("/{workflow_id}/execute", status_code=http_status.HTTP_202_ACCEPTED)
async def execute_workflow(
    workflow_id: str,
    request: WorkflowExecuteRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> ExecutionResponse:
    """Start a workflow execution. Security: JWT required, tenant isolated."""
    query = select(Workflow).where(
        and_(
            Workflow.workflow_id == workflow_id,
            Workflow.tenant_id == tenant_id,
            Workflow.is_active,
        )
    )

    if request.version:
        query = query.where(Workflow.version == request.version)
    else:
        query = query.order_by(Workflow.version.desc())

    result = await db.execute(query)
    workflow = result.scalars().first()

    if not workflow:
        raise_not_found("Workflow", workflow_id)

    if not workflow.nodes:
        # Een workflow zonder stappen liep tot "succeeded" zonder iets te doen (ADR-036 OP-13, gemeten 2026-10-22):
        # de klant ziet "klaar" terwijl er niets is gebeurd. Weigeren voordat er een uitvoering ontstaat.
        raise_validation_error(
            "De workflow heeft geen stappen; voeg eerst een stap toe voordat u hem start.",
            {"error": "WORKFLOW_ZONDER_STAPPEN", "workflow_id": workflow_id},
        )

    execution_id: str = "exec_%s" % uuid.uuid4().hex[:12]
    execution = WorkflowExecution(
        id=execution_id,
        execution_id=execution_id,
        workflow_id=workflow.id,
        tenant_id=tenant_id,
        status=WorkflowStatus.PENDING,
        input_json=request.input_data,
        output_json={},
        tasks_completed=0,
        tasks_failed=0,
        tasks_total=len(workflow.nodes or []),
        initiated_by=str(user_id),
    )

    db.add(execution)
    await db.flush()
    await db.commit()

    # Een uitvoering die niet naar de werker kan, is een 503 en geen stille 202 (ADR-036 OP-13).
    from src.workers.workflow_verzending import verstuur_workflow_taak

    await verstuur_workflow_taak(db, execution)

    return {
        "execution_id": execution_id,
        "workflow_id": workflow_id,
        "status": "pending",
        "message": "Workflow execution started",
    }


@router.get("/executions/{execution_id}", response_model=ExecutionStatusResponse)
async def get_execution_status(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    _: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> ExecutionStatusResponse:
    """Get execution status. Security: JWT required, tenant isolated."""
    query = select(WorkflowExecution).where(
        and_(
            WorkflowExecution.execution_id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    result = await db.execute(query)
    execution = result.scalars().first()

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    workflow_query = select(Workflow).where(Workflow.id == execution.workflow_id)
    workflow_result = await db.execute(workflow_query)
    workflow = workflow_result.scalars().first()

    taken_result = await db.execute(
        select(ExecutionTask)
        .where(
            and_(
                ExecutionTask.execution_id == execution.id,
                ExecutionTask.tenant_id == tenant_id,
            )
        )
        .order_by(ExecutionTask.created_at, ExecutionTask.task_ref)
    )
    # De knopen van de workflow dragen de naam die de medewerker de stap gaf; die staat niet in de taakrij.
    knopen = {
        str(knoop["id"]): knoop
        for knoop in (getattr(workflow, "nodes", None) or [])
        if isinstance(knoop, dict) and "id" in knoop
    }
    stappen = [stap_overzicht(taak, knopen) for taak in taken_result.scalars().all()]

    duration: float | None = None
    started_at = execution.started_at
    finished_at = execution.finished_at
    if started_at and finished_at:
        duration = (finished_at - started_at).total_seconds()

    return ExecutionStatusResponse(
        execution_id=execution.execution_id,
        workflow_id=workflow.workflow_id if workflow else "unknown",
        status=execution.status.value,
        input_data=execution.input_json or {},
        output_data=execution.output_json,
        start_time=_dt(started_at),
        end_time=_dt(finished_at),
        duration=duration,
        tasks_completed=execution.tasks_completed,
        tasks_failed=execution.tasks_failed,
        tasks_total=execution.tasks_total,
        error_message=execution.error_message,
        stappen=stappen,
    )


@router.get("/executions", response_model=list[ExecutionListItem])
async def list_executions(
    workflow_id: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    _: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> list[ExecutionListItem]:
    """List workflow executions with filtering. Security: JWT required, tenant isolated."""
    query = (
        select(WorkflowExecution)
        .options(selectinload(WorkflowExecution.workflow))
        .where(WorkflowExecution.tenant_id == tenant_id)
    )

    if workflow_id:
        query = query.join(Workflow).where(Workflow.workflow_id == workflow_id)

    if status_filter:
        try:
            status_enum = WorkflowStatus(status_filter)
            query = query.where(WorkflowExecution.status == status_enum)
        except ValueError:
            raise_validation_error(
                "Invalid status. Must be one of: %s" % [s.value for s in WorkflowStatus],
                {"invalid_status": status_filter},
            )

    query = query.order_by(WorkflowExecution.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    executions = result.scalars().all()

    items: list[ExecutionListItem] = []
    for e in executions:
        duration: float | None = None
        started_at = e.started_at
        finished_at = e.finished_at
        if started_at and finished_at:
            duration = (finished_at - started_at).total_seconds()

        items.append(
            ExecutionListItem(
                execution_id=e.execution_id,
                workflow_id=e.workflow.workflow_id if e.workflow else "unknown",
                status=e.status.value,
                start_time=_dt(started_at),
                end_time=_dt(finished_at),
                duration=duration,
            )
        )

    return items
