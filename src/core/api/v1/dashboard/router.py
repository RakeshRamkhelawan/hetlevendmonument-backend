"""
Dashboard v1 API endpoints.
Provides business-value summaries for the Business Dashboard UI.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth.api_deps import UserResponse, get_current_user
from .dependencies import DashboardService, get_dashboard_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/daily-summary")
async def get_daily_summary(
    current_user: UserResponse = Depends(get_current_user),
    service: DashboardService = Depends(get_dashboard_service),
) -> dict[str, object]:
    """Dagelijks waarde-overzicht voor het Business Dashboard."""
    logger.info(
        "daily summary requested",
        extra={"tenant_id": current_user.tenant_id, "user_id": current_user.id},
    )
    try:
        data = await service.get_daily_summary()
        return {"success": True, "data": data}
    except Exception as exc:
        logger.error(
            "daily summary failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": current_user.tenant_id},
        )
        raise HTTPException(status_code=500, detail="Internal error") from exc
