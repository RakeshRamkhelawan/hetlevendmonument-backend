"""
API endpoints for autonomous workflow execution using Dramatiq + Redis.
Feature 2: Autonomous Agents
"""

import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from src.core.api.dependencies import require_admin_user
from pydantic import BaseModel

from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/autonomous", tags=["autonomous-workflows"])


class ExecuteWorkflowRequest(BaseModel):
    """Request body for triggering workflow execution."""

    workflow_id: str
    initial_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class ExecuteWorkflowResponse(BaseModel):
    """Response for workflow execution trigger."""

    execution_id: str
    stream_key: str
    status: str


@router.post("/workflows/{workflow_id}/execute", response_model=ExecuteWorkflowResponse)
async def execute_workflow(
    workflow_id: str,
    request: ExecuteWorkflowRequest | None = None,
    current_user: User = Depends(require_admin_user),
) -> ExecuteWorkflowResponse:
    """
    Trigger asynchronous execution of a workflow.
    The workflow will run in the background via Dramatiq worker.
    Progress can be monitored via the returned stream_key using WebSocket.
    """
    # Import here to avoid circular import / load worker broker
    try:
        from src.core.tasks.workflow_tasks import execute_workflow_step
    except ImportError as e:
        logger.error("Dramatiq task import failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Background task system unavailable")

    execution_id = str(uuid4())
    stream_key = f"workflow:{execution_id}:progress"

    # Prepare the task data
    task_data = {
        "task_id": execution_id,
        "workflow_id": workflow_id,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "data": request.initial_data if request else {},
        "priority": 5,  # Medium priority
    }

    # Send to Dramatiq queue
    execute_workflow_step.send(task_data)

    logger.info("Workflow execution %s queued for workflow %s", execution_id, workflow_id)

    return ExecuteWorkflowResponse(
        execution_id=execution_id, stream_key=stream_key, status="queued"
    )
