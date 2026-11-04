"""ActivePieces execution sub-router: flow execution and run management."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from pydantic import BaseModel, Field

from src.core.exceptions.exceptions import SanskritiError
from src.core.activepieces.schemas import FlowRunRead
from src.core.activepieces.stappencontrole import NietToegestaneStap
from src.core.activepieces.service import ActivePiecesService, get_activepieces_service
from src.core.auth.api_deps import (
    UserResponse,
    get_current_user,
    require_resource_permission,
)
from src.core.api.v1.activepieces.dependencies import (
    integration_read_limit,
    integration_write_limit,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


class ExecuteFlowRequest(BaseModel):
    """Request to execute a flow."""

    payload: dict[str, object] = Field(default_factory=dict, description="Execution payload")
    synchronous: bool = Field(False, description="Wait for completion")
    timeout_seconds: int = Field(60, description="Timeout for synchronous execution", ge=1, le=300)


@router.post(
    "/flows/{flow_id}/execute",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Execute a flow",
    description="Trigger a flow execution.",
)
@integration_write_limit
async def execute_flow(
    http_request: Request,
    flow_id: str,
    request: ExecuteFlowRequest,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a flow with the given payload."""
    try:
        return await service.execute_flow(
            flow_id=flow_id,
            payload=request.payload,
            synchronous=request.synchronous,
            timeout_seconds=request.timeout_seconds,
        )
    except NietToegestaneStap as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get(
    "/flows/{flow_id}/runs",
    response_model=list[FlowRunRead],
    summary="List flow runs",
    description="Get execution history for a flow.",
)
@integration_read_limit
async def list_flow_runs(
    request: Request,
    flow_id: str,
    limit: int = Query(10, ge=1, le=100),
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[FlowRunRead]:
    """List recent runs for a flow."""
    try:
        return await service.get_flow_runs(flow_id, limit)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get(
    "/flows/{flow_id}/runs/{run_id}",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get run details",
    description="Get detailed information about a specific flow run.",
)
@integration_read_limit
async def get_flow_run(
    request: Request,
    _flow_id: str,
    run_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get details of a specific flow run."""
    try:
        return await service.get_flow_run(run_id)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/flows/{flow_id}/runs/{run_id}/retry",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Retry a failed run",
    description="Retry a failed flow run.",
)
@integration_write_limit
async def retry_flow_run(
    request: Request,
    _flow_id: str,
    run_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Retry a failed flow run."""
    try:
        return await service.retry_flow_run(run_id)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/flows/{flow_id}/runs/{run_id}/cancel",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Cancel a running flow",
    description="Cancel a currently running flow.",
)
@integration_write_limit
async def cancel_flow_run(
    request: Request,
    _flow_id: str,
    run_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Cancel a running flow run."""
    try:
        return await service.cancel_flow_run(run_id)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
