# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""ActivePieces flows sub-router: CRUD for flows."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from loguru import logger
from pydantic import BaseModel, Field

from src.core.exceptions.exceptions import SanskritiError
from src.core.activepieces.schemas import FlowRead
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


class FlowCreateRequest(BaseModel):
    """Request to create a new flow."""

    name: str = Field(..., description="Flow name")
    description: str | None = Field(None, description="Flow description")
    project_id: str | None = Field(
        None, description="Optional; only the tenant's own project is accepted"
    )
    react_flow_data: dict[str, object] = Field(..., description="React Flow graph definition")


class FlowUpdateRequest(BaseModel):
    """Request to update a flow."""

    name: str | None = Field(None, description="New flow name")
    description: str | None = Field(None, description="New description")
    react_flow_data: dict[str, object] | None = Field(None, description="Updated React Flow graph")
    status: str | None = Field(None, description="Flow status (ENABLED/DISABLED)")


class ValidationResponse(BaseModel):
    """Validation result response."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


@router.get(
    "/flows",
    response_model=list[FlowRead],
    summary="List all flows",
    description="Get all flows for the current tenant/project.",
)
@integration_read_limit
async def list_flows(
    request: Request,
    project_id: str | None = Query(None, description="Filter by project ID"),
    flow_status: str | None = Query(None, alias="status", description="Filter by status"),
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[FlowRead]:
    """List all flows with optional filtering."""
    try:
        return await service.list_flows(project_id=project_id, status=flow_status)
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get(
    "/flows/{flow_id}",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get flow details",
    description="Get detailed information about a specific flow.",
)
@integration_read_limit
async def get_flow(
    request: Request,
    flow_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detailed information about a specific flow."""
    try:
        return await service.get_flow(flow_id)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/flows",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Create a new flow",
    description="Create a new flow from a React Flow graph definition.",
    status_code=status.HTTP_201_CREATED,
)
@integration_write_limit
async def create_flow(
    http_request: Request,
    request: FlowCreateRequest,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a new flow from React Flow data."""
    try:
        return await service.create_flow(
            name=request.name,
            project_id=request.project_id,
            react_flow_data=request.react_flow_data,
            description=request.description,
        )
    except NietToegestaneStap as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        logger.opt(exception=True).error("create_flow mislukt: {}", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.put(
    "/flows/{flow_id}",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Update a flow",
    description="Update an existing flow.",
)
@integration_write_limit
async def update_flow(
    http_request: Request,
    flow_id: str,
    request: FlowUpdateRequest,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Update an existing flow."""
    try:
        return await service.update_flow(
            flow_id=flow_id,
            name=request.name,
            description=request.description,
            react_flow_data=request.react_flow_data,
            status=request.status,
        )
    except NietToegestaneStap as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except ValueError as e:
        logger.opt(exception=True).error("update_flow mislukt: {}", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.delete(
    "/flows/{flow_id}",
    summary="Delete a flow",
    description="Delete an existing flow.",
    status_code=status.HTTP_200_OK,
)
@integration_write_limit
async def delete_flow(
    request: Request,
    flow_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Delete a flow."""
    try:
        success = await service.delete_flow(flow_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete flow")
        return {"success": True}
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/flows/{flow_id}/toggle",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Toggle flow status",
    description="Enable or disable a flow.",
)
@integration_write_limit
async def toggle_flow(
    request: Request,
    flow_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
    _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Toggle flow enabled/disabled status."""
    try:
        return await service.toggle_flow(flow_id)
    except NietToegestaneStap as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/flows/validate",
    response_model=ValidationResponse,
    summary="Validate flow definition",
    description="Validate a React Flow or ActivePieces flow definition without creating it.",
)
@integration_write_limit
async def validate_flow_endpoint(
    request: Request,
    flow_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    flow_type: str = Query("react", description="Flow type: 'react' or 'activepieces'"),
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> ValidationResponse:
    """Validate a flow definition."""
    try:
        result = await service.validate_flow_definition(flow_data, flow_type)
        return ValidationResponse(
            valid=result.valid,
            errors=result.errors,
            warnings=result.warnings,
        )
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
