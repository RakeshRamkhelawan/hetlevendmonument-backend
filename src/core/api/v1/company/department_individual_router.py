"""Department Individual API Router

Endpoints for individual department operations (not under /companies).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.auth.api_deps import get_current_user
from src.core.company.department_service import DepartmentService
from src.core.company.schemas import DepartmentResponse, DepartmentUpdate
from src.core.container import TenantContext, container
from src.core.exceptions.exceptions import ConflictError, NotFoundError
from src.core.models.rbac_models import User

router = APIRouter(
    prefix="/departments",
    tags=["departments"],
    dependencies=[Depends(require_company_layer_enabled)],
)


def get_department_service(
    current_user: User = Depends(get_current_user),
) -> DepartmentService:
    """Get department service with tenant context from current user."""
    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )
    # Get DatabaseManager from container - DepartmentService expects the container's
    # DatabaseManager class (not the legacy one from database.database)
    db_manager = container.database_manager()
    return DepartmentService(
        db_manager=db_manager,
        tenant_context=tenant_context,
    )


@router.get(
    "/{dept_id}",
    response_model=DepartmentResponse,
    summary="Get department by ID",
)
async def get_department(
    dept_id: UUID,
    service: DepartmentService = Depends(get_department_service),
) -> DepartmentResponse:
    """Get department by ID.

    Args:
        dept_id: Department UUID

    Returns:
        Department details

    Raises:
        HTTPException: 404 if not found
    """
    department = await service.get_department(dept_id)
    if department is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Department {dept_id} not found",
        )
    return department


@router.put(
    "/{dept_id}",
    response_model=DepartmentResponse,
    summary="Update department",
)
async def update_department(
    dept_id: UUID,
    data: DepartmentUpdate,
    service: DepartmentService = Depends(get_department_service),
) -> DepartmentResponse:
    """Update department with optimistic locking.

    Args:
        dept_id: Department UUID
        data: Update data (include expected_version for optimistic locking)

    Returns:
        Updated department

    Raises:
        HTTPException: 404 if not found, 409 if version conflict
    """
    try:
        return await service.update_department(dept_id, data)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.delete(
    "/{dept_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete department",
    response_class=Response,
)
async def delete_department(
    dept_id: UUID,
    service: DepartmentService = Depends(get_department_service),
) -> None:
    """Delete department.

    Args:
        dept_id: Department UUID

    Raises:
        HTTPException: 404 if not found, 409 if has children
    """
    try:
        await service.delete_department(dept_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.post(
    "/{dept_id}/move",
    response_model=DepartmentResponse,
    summary="Move department to new parent",
)
async def move_department(
    dept_id: UUID,
    new_parent_id: UUID,
    service: DepartmentService = Depends(get_department_service),
) -> DepartmentResponse:
    """Move department to new parent.

    Args:
        dept_id: Department to move
        new_parent_id: New parent department

    Returns:
        Updated department

    Raises:
        HTTPException: 404 if not found, 409 if circular reference
    """
    try:
        return await service.move_department(dept_id, new_parent_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
