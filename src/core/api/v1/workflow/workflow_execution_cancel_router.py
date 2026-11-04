# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow execution cancel sub-router (SP-API-003 Dag 2).

Routes:
    POST /api/v1/workflows/executions/{execution_id}/cancel
    POST /api/v1/workflows/{execution_id}/cancel
    GET  /api/v1/workflows/{execution_id}/cancel-status
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.workflow.dependencies import get_db, OAuth2Scope
from src.core.auth.rbac_decorator import require_permission
from src.core.auth.api_deps import require_scopes as _require_scopes
from src.core.exceptions import raise_not_found, raise_workflow_error
from src.core.middleware.tenant_context import get_current_tenant_id as _get_current_tenant_id
from .dependencies import (
    CancellationScope,
    C7WorkflowExecution as WorkflowExecution,
    GracefulCanceller,
    WorkflowStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows-c7"])

ExecutionResponse = dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class CancelWorkflowRequest(BaseModel):
    """Request to cancel a workflow execution."""

    reason: str | None = Field(None, description="Optional reason for cancellation", max_length=500)


class CancelWorkflowResponse(BaseModel):
    """Response from workflow cancellation request."""

    success: bool = Field(..., description="Whether cancellation was successful")
    execution_id: str = Field(..., description="The workflow execution ID")
    cancelled_tasks: int = Field(0, description="Number of tasks cancelled")
    message: str = Field(..., description="Human-readable result message")


async def _get_tenant() -> int:
    """Get tenant ID from JWT context."""
    return _get_current_tenant_id()  # type: ignore[return-value]


# Global cancellation scope (singleton)
_cancellation_scope: CancellationScope | None = None


def get_cancellation_scope() -> CancellationScope:
    """Get or create the global cancellation scope."""
    global _cancellation_scope
    if _cancellation_scope is None:
        _cancellation_scope = CancellationScope()
    return _cancellation_scope


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> ExecutionResponse:
    """Cancel a running execution. Security: JWT required, tenant isolated."""
    from sqlalchemy import and_

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
