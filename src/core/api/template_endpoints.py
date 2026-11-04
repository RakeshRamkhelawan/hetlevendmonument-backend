# orphan:exempt reason: SP-API-010 proxy stub -- TODO(SP-API-011): migreer naar v1/company/template_router.py
"""
Template API Endpoints - deprecated proxy stubs.

GET /, GET /{id}, POST /{id}/instantiate, GET /search/ werkend behouden.
POST /{id}/deploy: stub (verboden import src.core.workflow.models verwijderd, ADR-033).
"""

from typing import Any
from typing import Optional as OptionalType

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import UserResponse, get_current_user_dependency, get_optional_user_dependency
from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.core.services.template_registry import get_template_registry
import logging
logger = logging.getLogger(__name__)

# Alias for testing compatibility
get_current_user = get_current_user_dependency

_DEPRECATION_SUNSET = "Thu, 01 Jan 2028 00:00:00 GMT"


class TemplateInstantiateRequest(BaseModel):
    """Request model for template instantiation"""

    workflow_name: str
    parameters: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


class TemplateResponse(BaseModel):
    """Response model for template data"""

    template_id: str
    name: str
    category: str
    description: str
    spec: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    required_integrations: list[str] | None = None
    author: str | None = None
    is_public: bool = False


router = APIRouter(
    prefix="/api/v1/workflow-templates",
    tags=["Workflow Templates"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", deprecated=True)
async def list_templates(
    response: Response,
    category: str | None = Query(None, description="Filter templates by category"),
    db: AsyncSession = Depends(get_db),
    current_user: OptionalType[UserResponse] = Depends(get_optional_user_dependency),
) -> list[TemplateResponse]:
    """List available templates, optionally filtered by category.

    Deprecated: use v1/company/template_router.py GET / (SP-API-011).
    """
    del current_user  # proxy stub -- geverifieerd door Depends
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    registry = get_template_registry()
    await registry.initialize(db)
    templates = registry.list_templates(category=category)
    return [
        TemplateResponse(
            template_id=t.template_id,
            name=t.name,
            category=t.category,
            description=t.description,
            spec=t.spec,
            required_integrations=t.required_integrations,
            author=t.author,
            is_public=t.is_public,
        )
        for t in templates
    ]


@router.get("/{template_id}", deprecated=True)
async def get_template(
    template_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> TemplateResponse:
    """Get template by ID.

    Deprecated: use v1/company/template_router.py GET /{template_id} (SP-API-011).
    """
    del current_user  # proxy stub -- geverifieerd door Depends
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    registry = get_template_registry()
    await registry.initialize(db)
    template = registry.get_template(template_id)
    if not template:
        raise NotFoundError("Template", template_id)
    return TemplateResponse(
        template_id=template.template_id,
        name=template.name,
        category=template.category,
        description=template.description,
        spec=template.spec,
        required_integrations=template.required_integrations,
        author=template.author,
        is_public=template.is_public,
    )


@router.post("/{template_id}/instantiate", deprecated=True)
async def instantiate_template(
    template_id: str,
    request: TemplateInstantiateRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create workflow from template.

    Deprecated: use v1/company/template_router.py POST /{template_id}/instantiate (SP-API-011).
    """
    del current_user  # proxy stub -- geverifieerd door Depends
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    registry = get_template_registry()
    await registry.initialize(db)
    try:
        spec = registry.instantiate(template_id, request.parameters)
    except ValueError:
        raise NotFoundError("Template", template_id)
    except Exception as e:
        logger.error("instantiate_template mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise ValidationError(
            "TEMPLATE_INSTANTIATION_FAILED", "Failed to instantiate template"
        )
    return {
        "workflow_name": request.workflow_name,
        "template_id": template_id,
        "spec": spec,
        "message": f"Template '{template_id}' instantiated successfully",
    }


@router.post("/{template_id}/deploy", deprecated=True)
async def deploy_template(
    template_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Deploy a template as a real workflow for the current tenant.

    Deprecated: no v1/ equivalent yet -- TODO(SP-API-011): maak POST /{id}/deploy aan in v1/company/.
    """
    del db, current_user  # proxy stub -- Depends enforce auth
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    # TODO(SP-API-011): C7Workflow (src.core.workflow.models) verwijderd -- verboden import ADR-033
    # TODO(SP-API-011): geen v1/company/template_router.py /{id}/deploy route -- aanmaken in SP-API-011
    return {
        "workflow_id": f"tpl_{template_id}",
        "db_id": None,
        "version": None,
        "message": "This endpoint is deprecated. Use v1/company/ when available (SP-API-011).",
        "url": None,
    }


@router.get("/search/", deprecated=True)
async def search_templates(
    response: Response,
    q: str = Query(..., description="Search query"),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> list[TemplateResponse]:
    """Search templates by name or description.

    Deprecated: no v1/ equivalent yet -- TODO(SP-API-011): maak GET /search/ aan in v1/company/.
    """
    del current_user  # proxy stub -- geverifieerd door Depends
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _DEPRECATION_SUNSET
    # TODO(SP-API-011): geen v1/company/template_router.py /search route -- aanmaken in SP-API-011
    registry = get_template_registry()
    await registry.initialize(db)
    all_templates = registry.list_templates()
    query_lower = q.lower()
    matching = [
        t
        for t in all_templates
        if query_lower in t.name.lower() or query_lower in t.description.lower()
    ]
    return [
        TemplateResponse(
            template_id=t.template_id,
            name=t.name,
            category=t.category,
            description=t.description,
            spec=t.spec,
            required_integrations=t.required_integrations,
            author=t.author,
            is_public=t.is_public,
        )
        for t in matching
    ]
