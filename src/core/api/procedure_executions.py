"""
# orphan:exempt reason: legacy pre-ADR-033 endpoint, pending Strangler Fig migration
FastAPI Router for Procedure Executions API
Provides REST endpoints for managing procedure execution lifecycle
"""

from typing import Any, Optional
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import db_manager
from src.core.procedures.procedure_execution_repository import ProcedureExecutionRepository
from src.core.procedures.schemas import (
    ProcedureExecutionCreate,
    ProcedureExecutionRead,
    ProcedureExecutionStatusUpdate,
)


# Mock dependencies - integrate with your auth system
async def get_db() -> AsyncIterator[AsyncSession]:
    """Get database session"""
    async with db_manager.get_async_session() as session:  # type: ignore[attr-defined]
        yield session


async def get_current_tenant_id() -> UUID:
    """
    Extract tenant ID from JWT token or headers
    Placeholder - implement based on your auth system
    """
    from uuid import uuid4

    return uuid4()


async def get_execution_repo(
    db: AsyncSession = Depends(get_db),
) -> ProcedureExecutionRepository:
    """Create repository instance"""
    return ProcedureExecutionRepository(db)


# Create router
router = APIRouter(
    prefix="/api/v1/procedure-executions",
    tags=["procedure-executions"],
    responses={401: {"description": "Unauthorized"}, 404: {"description": "Not found"}},
)


@router.get("", response_model=list[ProcedureExecutionRead])
async def list_executions(
    procedure_id: UUID | None = Query(None, description="Filter by procedure ID"),
    status: str | None = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureExecutionRepository = Depends(get_execution_repo),
) -> Sequence[ProcedureExecutionRead]:
    """
    List procedure executions with optional filtering

    Query Parameters:
    - procedure_id: Filter by specific procedure
    - status: Filter by execution status (pending_approval, running, completed, failed)
    - skip: Pagination offset
    - limit: Max results

    Returns: list[Any] of execution records  # TODO(TYPE): replace Any with concrete type
    """
    if status:
        executions = await repo.list_by_status(current_tenant_id, status)
    elif procedure_id:
        executions = await repo.list_by_procedure(current_tenant_id, procedure_id)
    else:
        executions = await repo.list_by_tenant(current_tenant_id, skip, limit)

    result = executions[skip : skip + limit] if not procedure_id and not status else executions
    return [ProcedureExecutionRead.model_validate(e) for e in result]


@router.get("/{execution_id}", response_model=ProcedureExecutionRead)
async def get_execution(
    execution_id: UUID,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureExecutionRepository = Depends(get_execution_repo),
) -> ProcedureExecutionRead:
    """
    Get specific procedure execution record

    Args:
        execution_id: Procedure execution ID

    Returns:
        Execution details including status, input/output, and audit trail

    Raises:
        404: If execution not found or belongs to different tenant
    """
    execution = await repo.get_by_id(current_tenant_id, execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    return execution


@router.post("", response_model=ProcedureExecutionRead, status_code=status.HTTP_201_CREATED)
async def create_execution(
    data: ProcedureExecutionCreate,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureExecutionRepository = Depends(get_execution_repo),
    db: AsyncSession = Depends(get_db),
) -> ProcedureExecutionRead:
    """
    Create new procedure execution record (Sprint 1: no actual execution yet)

    Args:
        data: Execution creation data (procedure_id and input)

    Returns:
        Created execution record with status 'pending_approval'

    Raises:
        404: If procedure not found
        422: If validation fails
    """
    execution = await repo.create(current_tenant_id, data)
    await db.commit()
    return execution


@router.patch("/{execution_id}/status", response_model=ProcedureExecutionRead)
async def update_execution_status(
    execution_id: UUID,
    data: ProcedureExecutionStatusUpdate,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureExecutionRepository = Depends(get_execution_repo),
    db: AsyncSession = Depends(get_db),
) -> ProcedureExecutionRead:
    """
    Update execution status and optionally set output/error

    Args:
        execution_id: Execution ID
        data: Status update data

    Returns:
        Updated execution record

    Raises:
        404: If execution not found
    """
    execution = await repo.update_status(current_tenant_id, execution_id, data)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )
    await db.commit()
    return execution


@router.get("/by-procedure/{procedure_id}", response_model=list[ProcedureExecutionRead])
async def list_executions_by_procedure(
    procedure_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureExecutionRepository = Depends(get_execution_repo),
) -> Sequence[ProcedureExecutionRead]:
    """
    Get all executions for a specific procedure

    Args:
        procedure_id: Procedure metadata ID
        skip: Pagination offset
        limit: Max results

    Returns: list[Any] of executions for this procedure  # TODO(TYPE): replace Any with concrete type
    """
    executions = await repo.list_by_procedure(current_tenant_id, procedure_id)
    return [ProcedureExecutionRead.model_validate(e) for e in executions[skip : skip + limit]]
