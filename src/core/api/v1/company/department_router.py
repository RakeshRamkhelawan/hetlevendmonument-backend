"""Department API Router

Endpoints for department CRUD operations under /companies.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.api.v1.users.schemas import UserResponse
from src.core.auth.api_deps import get_current_user
from src.core.company.department_service import DepartmentService
from src.core.company.schemas import DepartmentCreate, DepartmentResponse, OrgChartResponse
from src.core.container import TenantContext, container
from src.core.exceptions.exceptions import ConflictError, NotFoundError

router = APIRouter(
    prefix="/companies",
    tags=["departments"],
    dependencies=[Depends(require_company_layer_enabled)],
)


def get_department_service(
    current_user: UserResponse = Depends(get_current_user),
) -> DepartmentService:
    """Get department service with tenant context from current user."""
    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )
    return DepartmentService(
        db_manager=container.database_manager(),
        tenant_context=tenant_context,
    )


@router.post(
    "/{company_id}/departments",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new department",
)
async def create_department(
    company_id: UUID,
    data: DepartmentCreate,
    service: DepartmentService = Depends(get_department_service),
) -> DepartmentResponse:
    """Create a new department in a company.

    Args:
        company_id: Parent company ID
        data: Department creation data

    Returns:
        Created department

    Raises:
        HTTPException: 404 if company not found, 409 if validation fails
    """
    try:
        return await service.create_department(company_id, data)
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


@router.get(
    "/{company_id}/departments",
    response_model=OrgChartResponse,
    summary="Get organization chart",
)
async def get_org_chart(
    company_id: UUID,
    service: DepartmentService = Depends(get_department_service),
) -> OrgChartResponse:
    """Get organization chart for a company.

    Args:
        company_id: Company UUID

    Returns:
        Organization chart with tree structure
    """
    return await service.get_org_chart(company_id)
