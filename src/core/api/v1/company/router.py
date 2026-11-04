"""Company API Router

Endpoints for company CRUD operations.
"""

from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.auth.api_deps import get_current_user
from src.core.company.company_service import CompanyService
from src.core.company.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)
from src.core.container import TenantContext, container
from src.core.models.rbac_models import User

router = APIRouter(
    prefix="/companies",
    tags=["companies"],
    dependencies=[Depends(require_company_layer_enabled)],
)


def get_company_service(current_user: User = Depends(get_current_user)) -> CompanyService:
    """Get company service with tenant context from current user."""
    # Create tenant context from authenticated user
    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )
    return CompanyService(
        db_manager=container.database_manager(),
        tenant_context=tenant_context,
    )


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new company",
)
async def create_company(
    data: CompanyCreate,
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    """Create a new company.

    Args:
        data: Company creation data

    Returns:
        Created company
    """
    return await service.create_company(data)


@router.get(
    "",
    response_model=CompanyListResponse,
    summary="List all companies",
)
async def list_companies(
    service: CompanyService = Depends(get_company_service),
) -> CompanyListResponse:
    """List all companies for the current tenant.

    Returns: List[Any] of companies with department and goal counts  # TODO(TYPE): replace Any with concrete type
    """
    return await service.list_companies()


@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Get company by ID",
)
async def get_company(
    company_id: UUID,
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    """Get company by ID.

    Args:
        company_id: Company UUID

    Returns:
        Company details

    Raises:
        HTTPException: 404 if not found
    """
    company = await service.get_company(company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )
    return company


@router.put(
    "/{company_id}",
    response_model=CompanyResponse,
    summary="Update company",
)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    """Update company.

    Args:
        company_id: Company UUID
        data: Update data

    Returns:
        Updated company

    Raises:
        HTTPException: 404 if not found
    """
    company = await service.update_company(company_id, data)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )
    return company


@router.delete(
    "/{company_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete company",
    response_class=Response,
)
async def delete_company(
    company_id: UUID,
    service: CompanyService = Depends(get_company_service),
) -> None:
    """Delete company (soft delete).

    Args:
        company_id: Company UUID

    Raises:
        HTTPException: 404 if not found
    """
    deleted = await service.delete_company(company_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )


@router.post(
    "/{company_id}/export",
    response_model=dict,
    summary="Export company as template",
)
async def export_company_template(
    company_id: UUID,
    service: CompanyService = Depends(get_company_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Export company as template.

    Args:
        company_id: Company UUID

    Returns:
        Template dictionary (secrets scrubbed)

    Raises:
        HTTPException: 404 if not found
    """
    template = await service.export_as_template(company_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )
    return template
