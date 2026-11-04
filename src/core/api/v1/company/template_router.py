"""Template API Router - Company template management.

Provides endpoints for:
- Listing and filtering templates
- Getting template details
- Instantiating templates into companies
- Exporting companies as templates
- Contributing templates to marketplace

Architecture: docs/ARCHITECTURE_PAPERCLIP_INTEGRATION.md S.7.5
PRD: docs/3-PRDs/PRD_PAPERCLIP_INTEGRATION_v1.0.md S.4.5
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Optional, cast  # Any retained for cast(*) usage

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db, require_authenticated_user
from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.company.schemas import (
    CompanyResponse,
    TemplateContributeRequest,
    TemplateInstantiateRequest,
    TemplateListResponse,
    TemplateResponse,
)
from src.core.company.template_service import TemplateService
from src.core.api.v1.company.dependencies import DatabaseManager
from src.core.exceptions.exceptions import NotFoundError

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(require_company_layer_enabled)],
)


class SimpleTenantContext:
    """Simple tenant context for TemplateService."""

    tenant_id: int

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id


def get_template_service(
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),  # polymorphic: dict | UserResponse
) -> TemplateService:
    """Dependency to get TemplateService instance."""
    # Get tenant_id from current_user (handles both dict and UserResponse)
    if hasattr(current_user, "tenant_id"):
        # UserResponse object
        tenant_id = current_user.tenant_id  # pyright: ignore[reportAttributeAccessIssue]
    elif isinstance(current_user, dict):
        # Dictionary
        tenant_id = current_user.get("tenant_id", 1)
    else:
        # Fallback
        tenant_id = 1
    tenant_context = SimpleTenantContext(tenant_id)

    # Create a simple db manager wrapper
    class SimpleDBManager:
        _session: AsyncSession

        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        def get_session(self) -> object:
            class SessionContext:
                session: AsyncSession

                def __init__(self, session: AsyncSession) -> None:
                    self.session = session

                async def __aenter__(self) -> AsyncSession:
                    return self.session

                async def __aexit__(self, *args: Any) -> bool:
                    return False

            return SessionContext(self._session)

    # Cast SimpleDBManager to DatabaseManager for type compatibility
    db_manager = cast(DatabaseManager, SimpleDBManager(db))
    return TemplateService(db_manager, tenant_context)


@router.get(
    "",
    response_model=TemplateListResponse,
    summary="List available templates",
    description="List all templates accessible to the current tenant, with optional filtering.",
)
async def list_templates(
    company_type: Annotated[
        str | None,
        Query(description="Filter by company type (mkb, zzp, enterprise)"),
    ] = None,
    sector: Annotated[str | None, Query(description="Filter by sector")] = None,
    is_platform_template: Annotated[
        bool | None, Query(description="Filter by platform templates only")
    ] = None,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> TemplateListResponse:
    """List available company templates.

    Returns all templates the tenant has access to:
    - Platform templates (built-in)
    - Tenant-contributed templates

    Supports filtering by company type, sector, and platform template status.
    """
    filters: dict[str, str | bool] = {}
    if company_type:
        filters["company_type"] = company_type
    if sector:
        filters["sector"] = sector
    if is_platform_template is not None:
        filters["is_platform_template"] = is_platform_template

    templates = await template_service.list_templates(filters)

    return TemplateListResponse(
        templates=templates,
        total=len(templates),
    )


@router.get(
    "/search/",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Search templates",
    description="Search templates by keyword. Full implementation pending SP-API-012.",
)
async def search_templates(
    query: Annotated[str, Query(description="Search query")] = "",
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Search templates (stub -- full implementation in SP-API-012)."""
    return {
        "success": True,
        "data": {"query": query, "results": [], "total": 0, "limit": limit, "offset": offset},
    }


@router.post(
    "/{template_id}/deploy",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    status_code=status.HTTP_202_ACCEPTED,
    summary="Deploy template",
    description="Deploy a template to infrastructure. Full implementation pending SP-API-012.",
)
async def deploy_template(
    template_id: uuid.UUID,
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Deploy a template (stub -- full implementation in SP-API-012)."""
    return {"success": True, "data": {"template_id": str(template_id), "status": "pending"}}


@router.get(
    "/{template_id}",
    response_model=TemplateResponse,
    summary="Get template details",
    description="Get detailed information about a specific template.",
)
async def get_template(
    template_id: uuid.UUID,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> TemplateResponse:
    """Get a specific template by ID.

    Args:
        template_id: UUID of the template

    Returns:
        Template details

    Raises:
        404: Template not found
    """
    try:
        return await template_service.get_template(template_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{template_id}/instantiate",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Instantiate template",
    description="Create a new company based on a template.",
)
async def instantiate_template(
    template_id: uuid.UUID,
    data: TemplateInstantiateRequest,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> CompanyResponse:
    """Instantiate a template into a new company.

    Creates a new company using the specified template as a base.
    Includes all departments, goals, and configurations from the template.

    Args:
        template_id: UUID of the template to instantiate
        data: Instantiation request with company name and customizations

    Returns:
        Created company details

    Raises:
        404: Template not found
        422: Invalid instantiation data
    """
    try:
        return await template_service.instantiate(template_id, data)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/export/{company_id}",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Export company as template",
    description="Export a company's structure as a template definition.",
)
async def export_company(
    company_id: uuid.UUID,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Export a company as a template definition.

    Exports the company's structure (departments, goals, board config)
    as a template definition. Secrets are automatically scrubbed.

    Args:
        company_id: UUID of the company to export

    Returns:
        Template definition dictionary

    Raises:
        404: Company not found
    """
    try:
        return await template_service.export_company(company_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/contribute",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Contribute template",
    description="Contribute a new template to the marketplace.",
)
async def contribute_template(
    data: TemplateContributeRequest,
    template_service: TemplateService = Depends(get_template_service),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> TemplateResponse:
    """Contribute a template to the marketplace.

    Allows tenants to share their company configurations as templates
    for other tenants to use. Secrets are automatically scrubbed.

    Args:
        data: Template contribution request

    Returns:
        Created template details

    Raises:
        422: Invalid template data
    """
    return await template_service.contribute(
        name=data.name,
        company_type=data.company_type,
        sector=data.sector,
        description=data.description,
        template_definition=data.template_definition,
    )


@router.get(
    "/types/list",
    response_model=list[str],
    summary="List company types",
    description="Get list of available company types for filtering.",
)
async def list_company_types(
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> list[str]:
    """List available company types.

    Returns the list of supported company types that can be used
    for template filtering and creation.
    """
    return ["mkb", "zzp", "enterprise"]


@router.get(
    "/sectors/list",
    response_model=list[str],
    summary="List sectors",
    description="Get list of available sectors for filtering.",
)
async def list_sectors(
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> list[str]:
    """List available sectors.

    Returns the list of sectors that templates can be filtered by.
    """
    return [
        "Technologie",
        "Horeca",
        "Retail",
        "Consultancy",
        "Design",
        "Software Development",
        "Corporate",
        "Financiele Dienstverlening",
        "Gezondheidszorg",
    ]
