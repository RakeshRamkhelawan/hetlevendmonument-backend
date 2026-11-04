"""Compatibility router for procedures integration endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.api.v1.procedures.schemas import ProcedureExecutionRequest, ProcedureListResponse
from src.core.auth.api_deps import get_current_user

router = APIRouter(prefix="/procedures", tags=["Procedure Management"])


@router.get("/", response_model=ProcedureListResponse)
async def list_procedures(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> ProcedureListResponse:
    """List procedures for the current tenant with legacy pagination fields."""
    _ = (skip, current_user)
    return ProcedureListResponse(data=[], total=0, page=1, per_page=limit)


@router.get("/{procedure_id}")
async def get_procedure(
    procedure_id: int,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get a specific procedure by legacy integer identifier."""
    _ = current_user
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Procedure {procedure_id} not found",
    )


@router.post("/{procedure_id}/execute")
async def execute_procedure(
    procedure_id: int,
    request: ProcedureExecutionRequest,
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a specific procedure by legacy integer identifier."""
    _ = (request, current_user)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Procedure {procedure_id} not found",
    )
