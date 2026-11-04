# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
# NOTE: This file is kept for backward compatibility. The actual routes are
# split into workflow_execution_core_router.py (execute/status/list) and
# workflow_execution_cancel_router.py (cancel/cancel-status). SP-API-003 Dag 2.
"""
Workflow execution sub-router (SP-API-003) -- backward compat wrapper.

Actual routes split into:
    workflow_execution_core_router.py
    workflow_execution_cancel_router.py
"""

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, TypeAlias, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.api.v1.workflow.dependencies import get_db, OAuth2Scope
from src.core.auth.rbac_decorator import require_permission
from src.core.auth.api_deps import require_scopes as _require_scopes
from src.core.exceptions import raise_not_found, raise_validation_error, raise_workflow_error
from src.core.middleware.tenant_context import get_current_tenant_id as _get_current_tenant_id
from .dependencies import (
    CancellationScope,
    C7Workflow as Workflow,
    C7WorkflowExecution as WorkflowExecution,
    GracefulCanceller,
    WorkflowStatus,
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


class ExecutionListItem(BaseModel):
    """Execution list item."""

    execution_id: str
    workflow_id: str
    status: str
    start_time: str | None
    end_time: str | None
    duration: float | None


class CancelWorkflowRequest(BaseModel):
    """Request to cancel a workflow execution."""

    reason: str | None = Field(None, description="Optional reason for cancellation", max_length=500)


class CancelWorkflowResponse(BaseModel):
    """Response from workflow cancellation request."""

    success: bool = Field(..., description="Whether cancellation was successful")
    execution_id: str = Field(..., description="The workflow execution ID")
    cancelled_tasks: int = Field(0, description="Number of tasks cancelled")
    message: str = Field(..., description="Human-readable result message")


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


# Global cancellation scope (singleton)
_cancellation_scope: CancellationScope | None = None


def get_cancellation_scope() -> CancellationScope:
    """Get or create the global cancellation scope."""
    global _cancellation_scope
    if _cancellation_scope is None:
        _cancellation_scope = CancellationScope()
    return _cancellation_scope


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


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> ExecutionResponse:
    """Cancel a running execution. Security: JWT required, tenant isolated."""
    query = select(WorkflowExecution).where(
        and_(
            WorkflowExecution.execution_id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    result = await db.execute(query)
    execution = result.scalars().first()

    if not execution:
        raise_not_found("Execution", execution_id)

    if execution.status in [
        WorkflowStatus.SUCCEEDED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
    ]:
        raise_workflow_error(
            "Cannot cancel execution in %s status" % execution.status.value,
            {"execution_id": execution_id, "current_status": execution.status.value},
        )

    execution.status = WorkflowStatus.CANCELLED
    execution.finished_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "Execution cancelled",
        extra={"execution_id": execution_id, "tenant_id": tenant_id, "cancelled_by": str(user_id)},
    )

    return {
        "execution_id": execution_id,
        "status": "cancelled",
        "message": "Execution cancelled successfully",
    }


@router.post(
    "/{execution_id}/cancel",
    response_model=CancelWorkflowResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Cancel a workflow execution",
)
@require_permission("workflow:cancel")
async def cancel_workflow(
    execution_id: str,
    request: CancelWorkflowRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_current_tenant_id),
) -> CancelWorkflowResponse:
    """Cancel a workflow execution."""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.execution_id == execution_id)
    )
    execution = result.scalar_one_or_none()

    if execution is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Workflow execution '%s' not found" % execution_id,
        )

    if execution.tenant_id != tenant_id:
        logger.warning(
            "Tenant %s attempted to cancel execution %s belonging to tenant %s",
            tenant_id,
            execution_id,
            execution.tenant_id,
        )
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to cancel this workflow execution",
        )

    terminal_states = [
        WorkflowStatus.SUCCEEDED,
        WorkflowStatus.FAILED,
        WorkflowStatus.CANCELLED,
        WorkflowStatus.TIMEOUT,
    ]
    if execution.status in terminal_states:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Workflow execution is already %s and cannot be cancelled"
            % execution.status.value,
        )

    scope = get_cancellation_scope()
    canceller = GracefulCanceller(scope, graceful_timeout=30.0)
    cancel_result = await canceller.cancel_workflow(
        execution_id=execution_id, reason=request.reason or "Cancelled via API"
    )

    if cancel_result["success"]:
        execution.status = WorkflowStatus.CANCELLED
        execution.completed_at = datetime.now(timezone.utc)
        if request.reason:
            execution.error_message = "Cancelled: %s" % request.reason
        await db.commit()
        logger.info(
            "Workflow execution %s cancelled by tenant %s. Reason: %s",
            execution_id,
            tenant_id,
            request.reason,
        )
        return CancelWorkflowResponse(
            success=True,
            execution_id=execution_id,
            cancelled_tasks=1,
            message="Workflow execution '%s' has been cancelled successfully" % execution_id,
        )
    else:
        return CancelWorkflowResponse(
            success=False,
            execution_id=execution_id,
            cancelled_tasks=0,
            message=cancel_result.get("error", "Cancellation failed"),
        )


@router.get(
    "/{execution_id}/cancel-status",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get cancellation status",
)
async def get_cancellation_status(
    execution_id: str,
    tenant_id: int = Depends(_get_current_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get the cancellation status for a workflow execution."""
    scope = get_cancellation_scope()
    token = await scope.get_token(execution_id)

    if token is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="No active cancellation token found for execution '%s'" % execution_id,
        )

    return {
        "execution_id": execution_id,
        "is_cancelled": token.is_cancelled(),
        "cancelled_at": token.cancelled_at.isoformat() if token.cancelled_at else None,
        "reason": token.reason,
    }
