# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow execution via ActivePieces sub-router (SP-API-003 Dag 2).

Routes:
    POST /api/v1/workflows/execute
    GET  /api/v1/workflows/executions/{run_id}/status
    GET  /api/v1/workflows/flows/{flow_id}/executions
    GET  /api/v1/workflows/activepieces/health
"""

import logging
import uuid
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.activepieces.client import (
    UITVOERFOUT,
    ActivePiecesClient,
    ap_client_voor,
    get_activepieces_client,
)
from src.core.activepieces.stappencontrole import NietToegestaneStap, controleer_graaf
from src.core.api.v1.workflow.dependencies import get_db
from src.core.auth.api_deps import (
    UserResponse,
    get_current_user,
    require_resource_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflow-execution", "activepieces"])


# ============================================================================
# Request/Response Models
# ============================================================================


class WorkflowNode(BaseModel):
    """Node in workflow definition."""

    id: str
    label: str = ""
    agent_name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})


class WorkflowEdge(BaseModel):
    """Edge connecting workflow nodes."""

    id: str
    source: str
    target: str
    condition: str | None = None


class WorkflowExecuteRequest(BaseModel):
    """Request to execute a workflow via ActivePieces."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    project_id: str | None = Field(None, description="Optional AP project ID")


class WorkflowExecuteResponse(BaseModel):
    """Response from workflow execution."""

    success: bool
    message: str
    flow_id: str | None = None
    flow_name: str | None = None
    run_id: str | None = None
    status: str = "UNKNOWN"
    webhook_url: str | None = None
    project_id: str | None = None
    error: str | None = None


class ExecutionStatusResponse(BaseModel):
    """Response with execution status."""

    run_id: str
    status: str
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    output: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error: str | None = None


class ExecutionListResponse(BaseModel):
    """Response listing executions."""

    flow_id: str
    executions: list[dict[str, Any]] = Field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    count: int = 0


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/execute",
    response_model=WorkflowExecuteResponse,
    summary="Execute workflow via ActivePieces",
)
async def execute_workflow(
    request: WorkflowExecuteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> WorkflowExecuteResponse:
    """Execute a workflow definition via the ActivePieces automation engine."""
    correlation_id = str(uuid.uuid4())[:8]

    logger.info(
        "[%s] Execute workflow request: name=%s, nodes=%s, edges=%s",
        correlation_id,
        request.name,
        len(request.nodes),
        len(request.edges),
    )

    if not request.nodes:
        return WorkflowExecuteResponse(
            success=False,
            message="Workflow must have at least one node",
            status="INVALID",
        )

    workflow_dict = {
        "name": request.name,
        "description": request.description,
        "nodes": [node.model_dump() for node in request.nodes],
        "edges": [edge.model_dump() for edge in request.edges],
    }
    # Voor de client: zijn constructie of AP-verbinding mag een weigering niet veranderen
    # in een 200 met `success: False` (wfb-dag1 stap 1).
    try:
        controleer_graaf(workflow_dict)
    except NietToegestaneStap as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # De verbinding van DEZE tenant (uit het token). Ontbreekt die, dan is dat een 409 met een
    # duidelijke melding, geen 200 met `success: False`. `request.project_id` doen we bewust niet
    # mee: het project is dat van de verbinding, en de frontend stuurt hier het tenant-id in
    # (`WorkflowBuilder.tsx`), wat nooit een project-id was.
    ap_client = await ap_client_voor(current_user.tenant_id, db)

    try:
        result = await ap_client.execute_workflow(
            workflow_definition=workflow_dict,  # type: ignore[arg-type]
        )

        if result.get("success"):
            logger.info(
                "[%s] Workflow execution started: flow_id=%s, run_id=%s",
                correlation_id,
                result.get("flow_id"),
                result.get("run_id"),
            )
            return WorkflowExecuteResponse(
                success=True,
                message="Workflow execution started successfully",
                flow_id=cast(Optional[str], result.get("flow_id")),
                flow_name=cast(Optional[str], result.get("flow_name")),
                run_id=cast(Optional[str], result.get("run_id")),
                status=cast(str, result.get("status", "RUNNING")),
                webhook_url=cast(Optional[str], result.get("webhook_url")),
                project_id=cast(Optional[str], result.get("project_id")),
            )
        else:
            logger.error("[%s] Execution failed: %s", correlation_id, result.get("error"))
            return WorkflowExecuteResponse(
                success=False,
                message="Workflow execution failed",
                status="FAILED",
                error=UITVOERFOUT,
            )

    except NietToegestaneStap as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.error(
            "[%s] Execution error: %s: %s", correlation_id, type(e).__name__, e, exc_info=True
        )
        return WorkflowExecuteResponse(
            success=False,
            message="Execution error",
            status="ERROR",
            error=UITVOERFOUT,
        )


@router.get(
    "/executions/{run_id}/status",
    response_model=ExecutionStatusResponse,
    summary="Get execution status",
)
async def get_execution_status(
    run_id: str,
    ap_client: ActivePiecesClient = Depends(get_activepieces_client),
) -> ExecutionStatusResponse:
    """Get the status of a workflow execution."""
    try:
        result = await ap_client.get_run_logs(run_id)

        return ExecutionStatusResponse(
            run_id=run_id,
            status=cast(str, result.get("status", "UNKNOWN")),
            started_at=cast(Optional[str], result.get("started_at")),
            finished_at=cast(Optional[str], result.get("finished_at")),
            duration_ms=cast(Optional[int], result.get("duration_ms")),
            output=cast(Optional[dict[str, Any]], result.get("output")),
            error=cast(Optional[str], result.get("error")),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get execution status: %s: %s", type(e).__name__, e, exc_info=True)
        return ExecutionStatusResponse(
            run_id=run_id, status="ERROR", error="De status is nu niet op te halen."
        )


@router.get(
    "/flows/{flow_id}/executions",
    response_model=ExecutionListResponse,
    summary="List flow executions",
)
async def list_flow_executions(
    flow_id: str,
    limit: int = 10,
    ap_client: ActivePiecesClient = Depends(get_activepieces_client),
) -> ExecutionListResponse:
    """List recent executions for a flow."""
    try:
        executions = await ap_client.list_runs(flow_id, limit)
        return ExecutionListResponse(flow_id=flow_id, executions=executions, count=len(executions))
    except Exception as e:
        logger.error("Failed to list executions: %s: %s", type(e).__name__, e, exc_info=True)
        return ExecutionListResponse(flow_id=flow_id, executions=[], count=0)


@router.get(
    "/activepieces/health",
    summary="ActivePieces health check",
)
async def activepieces_health(
    ap_client: ActivePiecesClient = Depends(get_activepieces_client),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Check ActivePieces connectivity."""
    try:
        pieces = await ap_client.list_pieces()
        return {
            "status": "healthy",
            "activepieces_available": True,
            "pieces_count": len(pieces) if pieces else 0,
        }
    except Exception as e:
        # Geen `str(e)` naar de klant: een httpx-fout noemt het interne AP-adres.
        logger.warning("ActivePieces health degraded: %s: %s", type(e).__name__, e)
        return {
            "status": "degraded",
            "activepieces_available": False,
            "error": "ActivePieces is niet bereikbaar",
        }
