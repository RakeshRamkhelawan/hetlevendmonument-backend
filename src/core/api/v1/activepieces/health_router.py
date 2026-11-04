"""ActivePieces health sub-router: integration health checks."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.activepieces.service import ActivePiecesService, get_activepieces_service

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get(
    "/health",
    summary="Check integration health",
    description="Validates connectivity to the ActivePieces engine.",
)
async def check_integration_health(
    service: ActivePiecesService = Depends(get_activepieces_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Health check for ActivePieces integration."""
    health = await service.get_detailed_health()

    if health["is_available"]:
        return {
            "status": "healthy",
            "service": "activepieces",
            "details": health,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "service": "activepieces",
                "details": health,
            },
        )


@router.get(
    "/health/detailed",
    summary="Detailed health check",
    description="Get detailed health status including circuit breaker state.",
)
async def check_integration_health_detailed(
    service: ActivePiecesService = Depends(get_activepieces_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Detailed health check."""
    return await service.get_detailed_health()
