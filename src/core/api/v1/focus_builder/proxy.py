"""
FocusBuilder Service Proxy - Routes requests based on service mode.

This module provides the FocusBuilder router based on configuration:
- embedded: Use local FocusBuilder service (default, current behavior)
- remote: Forward requests to standalone FocusBuilder microservice

Usage:
    from src.core.api.v1.focus_builder.proxy import get_focus_builder_router
    router = get_focus_builder_router()
    app.include_router(router, prefix="/api/v1")
"""


import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from loguru import logger

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency,
    require_resource_permission,
)
from src.core.config.unified_config import get_config
from src.core.middleware.tenant_context import get_current_tenant_id

# =============================================================================
# HTTP Client for Remote Mode
# =============================================================================

_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create HTTP client for remote service calls."""
    global _http_client
    if _http_client is None:
        config = get_config()
        _http_client = httpx.AsyncClient(
            base_url=config.focusbuilder_service_url,
            timeout=30.0,
            follow_redirects=True,
        )
    return _http_client


async def close_http_client() -> None:
    """Close HTTP client on application shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


# =============================================================================
# Proxy Router (Remote Mode)
# =============================================================================


def create_proxy_router() -> APIRouter:
    """
    Create a proxy router that forwards all requests to remote FocusBuilder service.

    This enables the main backend to route FocusBuilder requests to a standalone
    microservice without changing the frontend API contract.
    """
    proxy_router = APIRouter(prefix="/focus-builder", tags=["FocusBuilder V1 (Proxy)"])

    async def forward_request(
        request: Request,
        path: str,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        """Forward request to remote FocusBuilder service."""
        client = await get_http_client()

        # Build target URL
        url = f"/api/v1/focus-builder{path}"

        # Forward headers (auth + tenant)
        headers = {
            "Authorization": request.headers.get("Authorization", ""),
            # NOTE: X-Tenant-ID is derived from the verified JWT context (Depends(get_current_tenant_id)),
            # NOT from the original client request. Safe because the proxy sits behind Traefik
            # and this header is never forwarded from untrusted sources.
            "X-Tenant-ID": str(tenant_id),
            "X-User-ID": str(current_user.id) if current_user else "",
            "Content-Type": request.headers.get("Content-Type", "application/json"),
        }

        # Get request body if present
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            body = await request.body()

        try:
            # Forward request
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body,
                params=dict(request.query_params),
            )

            # Return response with same status and content
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.headers.get("content-type"),
            )

        except httpx.ConnectError as e:
            logger.error(
                "FocusBuilder service unavailable: %s: %s", type(e).__name__, e, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="FocusBuilder service is currently unavailable",
            )
        except httpx.TimeoutException as e:
            logger.error("FocusBuilder service timeout: %s: %s", type(e).__name__, e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="FocusBuilder service request timed out",
            )
        except Exception as e:
            logger.error("FocusBuilder proxy error: %s: %s", type(e).__name__, e, exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Error forwarding request to FocusBuilder service",
            )

    # ==========================================================================
    # Proxy Endpoints (mirrors the consolidated router structure)
    # ==========================================================================

    # Flows CRUD
    @proxy_router.post("/flows")
    async def proxy_create_flow(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
        # Verdediging in de diepte (bevinding B): zonder `workflows:publish` stuurt de
        # proxy niets door naar de remote dienst.
        _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
    ) -> Response:
        return await forward_request(request, "/flows", current_user, tenant_id)

    @proxy_router.get("/flows")
    async def proxy_list_flows(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, "/flows", current_user, tenant_id)

    @proxy_router.get("/flows/{flow_id}")
    async def proxy_get_flow(
        flow_id: int,
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, f"/flows/{flow_id}", current_user, tenant_id)

    @proxy_router.put("/flows/{flow_id}")
    async def proxy_update_flow(
        flow_id: int,
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
        # Verdediging in de diepte (bevinding B): zonder `workflows:publish` stuurt de
        # proxy niets door naar de remote dienst.
        _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
    ) -> Response:
        return await forward_request(request, f"/flows/{flow_id}", current_user, tenant_id)

    @proxy_router.delete("/flows/{flow_id}")
    async def proxy_delete_flow(
        flow_id: int,
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
        # Verdediging in de diepte (bevinding B): zonder `workflows:publish` stuurt de
        # proxy niets door naar de remote dienst.
        _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
    ) -> Response:
        return await forward_request(request, f"/flows/{flow_id}", current_user, tenant_id)

    # Execution
    @proxy_router.post("/flows/{flow_id}/execute")
    async def proxy_execute_flow(
        flow_id: int,
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
        # Verdediging in de diepte (bevinding B): zonder `workflows:publish` stuurt de
        # proxy niets door naar de remote dienst.
        _publiceren: int = Depends(require_resource_permission("workflows", "publish")),
    ) -> Response:
        return await forward_request(request, f"/flows/{flow_id}/execute", current_user, tenant_id)

    @proxy_router.get("/flows/{flow_id}/runs")
    async def proxy_get_runs(
        flow_id: int,
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, f"/flows/{flow_id}/runs", current_user, tenant_id)

    @proxy_router.get("/flows/{flow_id}/runs/{run_id}")
    async def proxy_get_run(
        flow_id: int,
        run_id: str,
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(
            request, f"/flows/{flow_id}/runs/{run_id}", current_user, tenant_id
        )

    # Pieces Catalog
    @proxy_router.get("/pieces")
    async def proxy_list_pieces(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, "/pieces", current_user, tenant_id)

    @proxy_router.post("/pieces/sync")
    async def proxy_sync_pieces(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, "/pieces/sync", current_user, tenant_id)

    # AI Suggestions
    @proxy_router.post("/ai/suggest")
    async def proxy_ai_suggest(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, "/ai/suggest", current_user, tenant_id)

    @proxy_router.post("/ai/generate")
    async def proxy_ai_generate(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, "/ai/generate", current_user, tenant_id)

    # Validation
    @proxy_router.post("/validate")
    async def proxy_validate(
        request: Request,
        current_user: UserResponse = Depends(
            get_current_user_dependency
        ),
        tenant_id: int = Depends(get_current_tenant_id),
    ) -> Response:
        return await forward_request(request, "/validate", current_user, tenant_id)

    # Health check for remote service
    @proxy_router.get("/health")
    async def proxy_health(request: Request) -> JSONResponse:
        """Check remote FocusBuilder service health."""
        try:
            client = await get_http_client()
            response = await client.get("/health")
            return JSONResponse(
                content=response.json(),
                status_code=response.status_code,
            )
        except Exception as e:
            logger.warning(
                "FocusBuilder health check failed: %s: %s", type(e).__name__, e, exc_info=True
            )
            return JSONResponse(
                content={"status": "unavailable", "error": "Er is een fout opgetreden."},
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

    return proxy_router


# =============================================================================
# Router Factory
# =============================================================================


def get_focus_builder_router() -> APIRouter:
    """
    Get the appropriate FocusBuilder router based on configuration.

    Returns:
        - In embedded mode: The direct FocusBuilder router (local service)
        - In remote mode: A proxy router that forwards to standalone service

    Configuration: str FOCUSBUILDER_SERVICE_MODE environment variable:
        - embedded (default): Run FocusBuilder as part of main backend
        - remote: Route requests to standalone FocusBuilder service
    """
    config = get_config()
    mode = config.focusbuilder_service_mode.lower()

    if mode == "remote":
        logger.info(
            f"FocusBuilder: Remote mode enabled, proxying to {config.focusbuilder_service_url}"
        )
        return create_proxy_router()
    else:
        # Default: embedded mode - use local router
        logger.info("FocusBuilder: Embedded mode (local service)")
        from src.core.api.v1.focus_builder.router import router

        return router


def is_remote_mode() -> bool:
    """Check if FocusBuilder is running in remote mode."""
    config = get_config()
    mode_value = str(config.focusbuilder_service_mode)
    return mode_value.lower() == "remote"
