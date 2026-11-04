"""
# orphan:exempt reason: legacy pre-ADR-033 endpoint, pending Strangler Fig migration
FastAPI Router for Procedures API
Provides REST endpoints for querying procedure metadata
"""

from datetime import datetime, timezone
from typing import Any, Optional
from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import db_manager
from src.core.procedures.procedures_repository import ProcedureMetadataRepository
from src.core.procedures.schemas import (
    ProcedureExecutionCreate,
    ProcedureExecutionRead,
    ProcedureMetadataRead,
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


async def get_procedure_repo(
    db: AsyncSession = Depends(get_db),
) -> ProcedureMetadataRepository:
    """Create repository instance"""
    return ProcedureMetadataRepository(db)


# Create router
router = APIRouter(
    prefix="/api/v1/procedures",
    tags=["procedures"],
    responses={401: {"description": "Unauthorized"}, 404: {"description": "Not found"}},
)


@router.get("", response_model=list[ProcedureMetadataRead])
async def list_procedures(
    domain_pack_id: UUID | None = Query(None, description="Filter by domain pack ID"),
    is_platform_template: bool | None = Query(
        None, description="Filter by platform template status"
    ),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureMetadataRepository = Depends(get_procedure_repo),
) -> Sequence[ProcedureMetadataRead]:
    """
    List procedures with optional filtering and pagination

    Query Parameters:
    - domain_pack_id: Filter by specific domain pack
    - is_platform_template: Filter by template status
    - skip: Pagination offset
    - limit: Pagination limit (max 500)

    Returns: list[Any] of procedure metadata  # TODO(TYPE): replace Any with concrete type
    """
    procedures = await repo.search(
        current_tenant_id,
        domain_pack_id=domain_pack_id,
        is_platform_template=is_platform_template,
    )
    # Apply pagination on results and convert to read schema
    return [ProcedureMetadataRead.model_validate(p) for p in procedures[skip : skip + limit]]


@router.get("/{procedure_id}", response_model=ProcedureMetadataRead)
async def get_procedure(
    procedure_id: UUID,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureMetadataRepository = Depends(get_procedure_repo),
) -> ProcedureMetadataRead:
    """
    Get specific procedure metadata

    Args:
        procedure_id: Procedure metadata ID

    Returns:
        Procedure metadata details

    Raises:
        404: If procedure not found or belongs to different tenant
    """
    procedure = await repo.get_by_id(current_tenant_id, procedure_id)
    if not procedure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedure {procedure_id} not found",
        )
    return procedure


@router.get("/search", response_model=list[ProcedureMetadataRead])
async def search_procedures(
    q: str | None = Query(None, description="Search by category or description"),
    tags: list[str] | None = Query(
        None, description="Filter by intent tags (comma-separated or multiple params)"
    ),
    category: str | None = Query(None, description="Filter by category"),
    domain_pack_id: UUID | None = Query(None, description="Filter by domain pack ID"),
    is_platform_template: bool | None = Query(None, description="Filter by template status"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureMetadataRepository = Depends(get_procedure_repo),
) -> Sequence[ProcedureMetadataRead]:
    """
    Search procedures with multiple filter options

    Query Parameters:
    - q: Text search in category/description
    - tags: Intent tags to filter by (any match)
    - category: Exact/partial category match
    - domain_pack_id: Domain pack filter
    - is_platform_template: Template status filter
    - skip: Pagination offset
    - limit: Max results (1-500)

    Returns: list[Any] of matching procedure metadata  # TODO(TYPE): replace Any with concrete type
    """
    # Use text search 'q' for category if provided
    search_category = q or category

    procedures = await repo.search(
        current_tenant_id,
        tags=tags,
        category=search_category,
        domain_pack_id=domain_pack_id,
        is_platform_template=is_platform_template,
    )

    # Apply pagination and convert to read schema
    return [ProcedureMetadataRead.model_validate(p) for p in procedures[skip : skip + limit]]


@router.get("/by-flow/{flow_id}", response_model=ProcedureMetadataRead)
async def get_procedure_by_flow(
    flow_id: UUID,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureMetadataRepository = Depends(get_procedure_repo),
) -> ProcedureMetadataRead:
    """
    Get procedure metadata by FocusBuilderFlow ID

    Args:
        flow_id: FocusBuilderFlow ID

    Returns:
        Procedure metadata linked to this flow

    Raises:
        404: If no procedure found for this flow
    """
    procedure = await repo.get_by_flow_id(current_tenant_id, flow_id)
    if not procedure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedure with flow {flow_id} not found",
        )
    return procedure


@router.get("/tags/{tag}", response_model=list[ProcedureMetadataRead])
async def get_procedures_by_tag(
    tag: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureMetadataRepository = Depends(get_procedure_repo),
) -> Sequence[ProcedureMetadataRead]:
    """
    Get all procedures with specific intent tag

    Args:
        tag: Intent tag to search for
        skip: Pagination offset
        limit: Max results

    Returns: list[Any] of procedures with the tag  # TODO(TYPE): replace Any with concrete type
    """
    procedures = await repo.search_by_intent_tags(current_tenant_id, [tag])
    return [ProcedureMetadataRead.model_validate(p) for p in procedures[skip : skip + limit]]


@router.get("/unauthorized_401", status_code=status.HTTP_401_UNAUTHORIZED)
async def unauthorized_example() -> None:
    """Example endpoint - auth validation happens via dependencies"""
    pass


@router.post(
    "/execute",
    response_model=ProcedureExecutionRead,
    status_code=status.HTTP_201_CREATED,
)
async def execute_procedure(
    data: ProcedureExecutionCreate,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    repo: ProcedureMetadataRepository = Depends(get_procedure_repo),
    db: AsyncSession = Depends(get_db),
) -> ProcedureExecutionRead:
    """
    Execute a procedure

    Args:
        data: Execution creation data with procedure_id

    Returns:
        Created procedure execution with status pending_approval or running

    Raises:
        404: If procedure not found or belongs to different tenant
        422: If procedure is not active
    """
    from src.core.procedures.procedure_execution_repository import ProcedureExecutionRepository

    # Verify procedure exists and belongs to tenant
    procedure = await repo.get_by_id(current_tenant_id, data.procedure_id)
    if not procedure:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedure {data.procedure_id} not found",
        )

    # Check if procedure is active
    if procedure.status != "active":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Procedure {data.procedure_id} is not active (status: {procedure.status})",
        )

    # Create execution record
    exec_repo = ProcedureExecutionRepository(db)
    execution = await exec_repo.create(tenant_id=current_tenant_id, data=data)

    await db.commit()
    await db.refresh(execution)

    # Convert to read schema
    from src.core.procedures.schemas import ProcedureExecutionRead

    return ProcedureExecutionRead.model_validate(execution)


@router.post("/{execution_id}/approve", response_model=ProcedureExecutionRead)
async def approve_execution(
    execution_id: UUID,
    current_tenant_id: UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> ProcedureExecutionRead:
    """
    Approve a pending procedure execution

    Args:
        execution_id: Execution ID to approve

    Returns:
        Updated execution with status 'running' or 'completed'

    Raises:
        404: If execution not found or belongs to different tenant
        422: If execution is not in pending_approval state
    """
    from src.core.procedures.procedure_execution_repository import ProcedureExecutionRepository
    from src.core.procedures.schemas import ProcedureExecutionStatusUpdate

    exec_repo = ProcedureExecutionRepository(db)

    # Get execution
    execution = await exec_repo.get_by_id(current_tenant_id, execution_id)
    if not execution:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Execution {execution_id} not found",
        )

    # Check if in pending_approval state
    if execution.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Execution {execution_id} is not pending approval (status: {execution.status})",
        )

    # Update status to running
    update_data = ProcedureExecutionStatusUpdate(status="running")
    execution = await exec_repo.update_status(
        tenant_id=current_tenant_id, execution_id=execution_id, data=update_data
    )

    if execution is None:
        raise HTTPException(
            status_code=404,
            detail=f"Execution {execution_id} not found after update",
        )

    # Add audit entry
    audit_entry = {
        "action": "approved",
        "approved_by": str(current_tenant_id),  # TODO: Get actual user ID
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    execution.audit_trail.append(audit_entry)

    await db.commit()
    await db.refresh(execution)

    # Convert to read schema
    from src.core.procedures.schemas import ProcedureExecutionRead

    return ProcedureExecutionRead.model_validate(execution)
