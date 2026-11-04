# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""ActivePieces connections sub-router: connection CRUD and OAuth."""

import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from loguru import logger
from pydantic import BaseModel, Field

from src.core.exceptions import ValidatieFout
from src.core.exceptions.exceptions import SanskritiError
from src.core.activepieces.client import ActivePiecesClient, get_activepieces_client
from src.core.activepieces.schemas import ConnectionCreate, ConnectionRead
from src.core.activepieces.service import ActivePiecesService, get_activepieces_service
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.api.v1.activepieces.dependencies import (
    KoppelAudit,
    get_koppel_audit,
    integration_read_limit,
    integration_write_limit,
    require_koppel_beheerder,
)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


class ConnectionUpdateRequest(BaseModel):
    """Request to update a connection."""

    name: str | None = Field(None, description="New connection name")
    value: dict[str, object] | None = Field(None, description="Updated connection configuration")


class ConnectionTestResult(BaseModel):
    """Result of connection test."""

    success: bool
    message: str
    details: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class OAuthUrlResponse(BaseModel):
    """Response with OAuth URL."""

    oauth_url: str = Field(..., description="OAuth authorization URL")
    state: str = Field(..., description="State parameter for security")


class OAuthCallbackResponse(BaseModel):
    """Response after OAuth callback."""

    success: bool
    connection_id: str | None = None
    message: str


@router.get(
    "/connections",
    response_model=list[ConnectionRead],
    summary="List all connections",
    description="Get all app connections for the current tenant.",
)
@integration_read_limit
async def list_connections(
    request: Request,
    app_name: str | None = Query(None, description="Filter by app name"),
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> list[ConnectionRead]:
    """List all app connections."""
    try:
        return await service.list_connections(app_name=app_name)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get(
    "/connections/{connection_id}",
    response_model=ConnectionRead,
    summary="Get connection details",
    description="Get details about a specific connection.",
)
@integration_read_limit
async def get_connection(
    request: Request,
    connection_id: str,
    service: ActivePiecesService = Depends(get_activepieces_service),
    _current_user: UserResponse = Depends(get_current_user),
) -> ConnectionRead:
    """Get connection details (without sensitive data)."""
    try:
        return await service.get_connection(connection_id)
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/connections",
    response_model=ConnectionRead,
    summary="Create a connection",
    description="Create a new app connection.",
    status_code=status.HTTP_201_CREATED,
)
@integration_write_limit
async def create_connection(
    http_request: Request,
    request: ConnectionCreate,
    _current_user: UserResponse = Depends(require_koppel_beheerder),
    audit: KoppelAudit = Depends(get_koppel_audit),
    service: ActivePiecesService = Depends(get_activepieces_service),
) -> ConnectionRead:
    """Create a new app connection."""
    try:
        aangemaakt = await service.create_connection(request)
        await audit.schrijf(
            "AP_VERBINDING_AANGEMAAKT",
            "POST",
            {
                "app_name": aangemaakt.app_name,
                "connection_id": aangemaakt.id,
            },
        )
        return aangemaakt
    except ValidatieFout as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValueError as e:
        logger.opt(exception=True).error("create_connection mislukt: {}", type(e).__name__)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.delete(
    "/connections/{connection_id}",
    summary="Delete a connection",
    description="Delete an app connection.",
    status_code=status.HTTP_200_OK,
)
@integration_write_limit
async def delete_connection(
    request: Request,
    connection_id: str,
    _current_user: UserResponse = Depends(require_koppel_beheerder),
    audit: KoppelAudit = Depends(get_koppel_audit),
    service: ActivePiecesService = Depends(get_activepieces_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Delete a connection."""
    try:
        bestaand = await service.get_connection(connection_id)
        await service.delete_connection(connection_id)
        await audit.schrijf(
            "AP_VERBINDING_VERWIJDERD",
            "DELETE",
            {
                "app_name": bestaand.app_name,
                "connection_id": connection_id,
            },
        )
        return {"success": True}
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.post(
    "/connections/{connection_id}/test",
    response_model=ConnectionTestResult,
    summary="Test a connection",
    description="Test if a connection is valid and working.",
)
@integration_write_limit
async def test_connection(
    request: Request,
    connection_id: str,
    _current_user: UserResponse = Depends(require_koppel_beheerder),
    audit: KoppelAudit = Depends(get_koppel_audit),
    service: ActivePiecesService = Depends(get_activepieces_service),
) -> ConnectionTestResult:
    """Test a connection."""
    try:
        result = await service.test_connection(connection_id)
        return ConnectionTestResult(
            success=result.get("success", False),
            message=result.get("message", ""),
            details=result.get("details"),
        )
    except HTTPException as e:
        if e.status_code == 400:
            return ConnectionTestResult(
                success=False,
                message="Connection test failed",
                details={"error": e.detail},
            )
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.put(
    "/connections/{connection_id}",
    response_model=ConnectionRead,
    summary="Update a connection",
    description="Update an existing app connection.",
)
@integration_write_limit
async def update_connection(
    http_request: Request,
    connection_id: str,
    request: ConnectionUpdateRequest,
    _current_user: UserResponse = Depends(require_koppel_beheerder),
    audit: KoppelAudit = Depends(get_koppel_audit),
    service: ActivePiecesService = Depends(get_activepieces_service),
) -> ConnectionRead:
    """Update an existing connection."""
    try:
        bijgewerkt = await service.update_connection(
            connection_id=connection_id,
            name=request.name,
            value=request.value,
        )
        await audit.schrijf(
            "AP_VERBINDING_GEWIJZIGD",
            "PUT",
            {
                "app_name": bijgewerkt.app_name,
                "connection_id": bijgewerkt.id,
                "naam_gewijzigd": request.name is not None,
                "sleutel_gewijzigd": bool(request.value),
            },
        )
        return bijgewerkt
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.exception("Unexpected error: {}", e)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get(
    "/connections/oauth/{app_name}/url",
    response_model=OAuthUrlResponse,
    summary="Get OAuth URL",
    description="Generate OAuth authorization URL for an app.",
)
@integration_read_limit
async def get_oauth_url(
    request: Request,
    app_name: str,
    redirect_uri: str = Query(..., description="Redirect URI after authorization"),
    _current_user: UserResponse = Depends(require_koppel_beheerder),
    client: ActivePiecesClient = Depends(get_activepieces_client),
) -> OAuthUrlResponse:
    """Get OAuth authorization URL for an app."""
    state = secrets.token_urlsafe(32)
    try:
        result = await client._make_request(
            "POST",
            f"/connections/oauth/{app_name}/url",
            "get_oauth_url",
            json_data={
                "redirectUri": redirect_uri,
                "state": state,
            },
        )

        oauth_url = result.get("oauthUrl")
        if not oauth_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth URL not returned by ActivePieces",
            )

        return OAuthUrlResponse(
            oauth_url=str(oauth_url),
            state=state,
        )
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.error("OAuth URL error for %s: %s: %s", app_name, type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OAuth not available for this integration",
        )


@router.post(
    "/connections/oauth/callback",
    response_model=OAuthCallbackResponse,
    summary="OAuth callback",
    description="Handle OAuth callback and create connection.",
)
@integration_write_limit
async def oauth_callback(
    request: Request,
    app_name: str = Query(..., description="App name"),
    code: str = Query(..., description="Authorization code"),
    state: str = Query(..., description="State parameter"),
    project_id: str | None = Query(None, description="Optional; only the own project is accepted"),
    connection_name: str | None = Query(None, description="Connection name"),
    _current_user: UserResponse = Depends(require_koppel_beheerder),
    client: ActivePiecesClient = Depends(get_activepieces_client),
    audit: KoppelAudit = Depends(get_koppel_audit),
) -> OAuthCallbackResponse:
    """Handle OAuth callback and create connection."""
    project_id = client.eigen_project(project_id)
    try:
        result = await client._make_request(
            "POST",
            "/connections/oauth/callback",
            "oauth_callback",
            json_data={
                "appName": app_name,
                "code": code,
                "state": state,
                "projectId": project_id,
                "name": connection_name or f"{app_name}_connection",
            },
        )

        nieuw_id = str(result.get("id")) if result.get("id") is not None else None
        await audit.schrijf(
            "AP_VERBINDING_AANGEMAAKT",
            "POST",
            {"app_name": app_name, "connection_id": nieuw_id, "via": "oauth"},
        )
        return OAuthCallbackResponse(
            success=True,
            connection_id=nieuw_id,
            message="Connection created successfully",
        )
    except HTTPException:
        raise
    except SanskritiError:
        raise
    except Exception as e:
        logger.error("OAuth callback connection error: %s: %s", type(e).__name__, e, exc_info=True)
        return OAuthCallbackResponse(
            success=False,
            message="Failed to create connection",
        )
