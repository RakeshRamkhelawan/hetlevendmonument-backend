"""Tools integrations sub-router (ADR-033 Laag 1) -- catalog and search stubs."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from src.core.api.dependencies import require_authenticated_user

integrations_router = APIRouter(tags=["Tool Management"])


@integrations_router.get(
    "/integrations/catalog",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="List integration catalog",
    description="List available tool integrations. Full implementation pending SP-API-012.",
)
async def list_integration_catalog(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List integration catalog (stub -- full implementation in SP-API-012)."""
    return {"success": True, "data": {"items": [], "total": 0, "limit": limit, "offset": offset}}


@integrations_router.get(
    "/integrations/search",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Search integrations",
    description="Search available tool integrations. Full implementation pending SP-API-012.",
)
async def search_integrations(
    query: Annotated[str, Query(description="Search query")] = "",
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _authenticated: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Search integrations (stub -- full implementation in SP-API-012)."""
    return {
        "success": True,
        "data": {"query": query, "items": [], "total": 0, "limit": limit, "offset": offset},
    }
