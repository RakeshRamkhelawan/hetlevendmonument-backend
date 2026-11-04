"""Health check sub-router: liveness, readiness, DB diagnostics, deep, paperclip.

ADR-012: 3-tier health checks for Kubernetes.
ADR-033 Laag 1 sub-router (max 200 lines).
"""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.health.dependencies import get_db, verify_token

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check() -> JSONResponse:
    """Liveness probe (ADR-012). Delegates to health_endpoints."""
    from src.core.api.health_endpoints import health_check as _health_check

    return await _health_check()


@router.get("/health/ready", status_code=status.HTTP_200_OK, tags=["Health"])
async def readiness_check(request: Request, response: Response) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Readiness probe (ADR-012). Delegates to health_endpoints."""
    from src.core.api.health_endpoints import readiness_check as _readiness_check

    return await _readiness_check(request=request, response=response)


@router.get("/health/db", status_code=status.HTTP_200_OK, tags=["Health"])
async def db_health_check(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    authenticated: bool = Depends(verify_token),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Database health diagnostics (ADR-012). Auth required. Delegates to health_endpoints."""
    from src.core.api.health_endpoints import db_health_check as _db_health_check

    return await _db_health_check(
        request=request, response=response, db=db, authenticated=authenticated
    )


@router.get("/ready", status_code=status.HTTP_200_OK, deprecated=True, tags=["Health"])
async def readiness_check_legacy(request: Request, response: Response) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """DEPRECATED: Use /health/ready instead. Legacy readiness endpoint."""
    from src.core.api.health_endpoints import readiness_check_legacy as _readiness_check_legacy

    return await _readiness_check_legacy(request=request, response=response)


@router.get("/health/deep", status_code=status.HTTP_200_OK, tags=["Health"])
async def deep_health_check(
    request: Request,
    response: Response,
    authenticated: bool = Depends(verify_token),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Deep health diagnostics (ADR-012). Auth required. Delegates to health_endpoints."""
    from src.core.api.health_endpoints import deep_health_check as _deep_health_check

    return await _deep_health_check(request=request, response=response, authenticated=authenticated)


@router.get("/health/paperclip", tags=["Health"])
async def paperclip_health() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Paperclip pipeline health check. Delegates to health_endpoints."""
    from src.core.api.health_endpoints import paperclip_health as _paperclip_health

    return await _paperclip_health()
