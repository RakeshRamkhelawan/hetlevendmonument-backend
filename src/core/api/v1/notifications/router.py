"""
Notification REST Router - CRUD endpoints for in-app notification inbox.

Provides paginated access and read status toggles with strict tenant isolation.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .dependencies import NotificationsService, get_notifications_service
from .schemas import NotificationListResponse, NotificationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List notifications",
    description="Retrieve a paginated list of notifications for the current user and tenant.",
)
async def list_notifications(
    service: NotificationsService = Depends(get_notifications_service),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    unread_only: bool = Query(False),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Retrieve notifications with pagination and tenant isolation."""
    result = await service.list_notifications(limit=limit, offset=offset, unread_only=unread_only)
    return {
        "success": True,
        "data": [NotificationResponse.model_validate(n) for n in result["items"]],
        "total": result["total"],
        "limit": limit,
        "offset": offset,
    }


@router.post(
    "/mark-all-read",
    summary="Mark all notifications as read",
    description="Mark all unread notifications as read for the current user.",
)
async def mark_all_read(
    service: NotificationsService = Depends(get_notifications_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Mark all user notifications read."""
    count = await service.mark_all_read()
    return {"success": True, "count": count}


@router.post(
    "/{notification_id}/read",
    summary="Mark single notification as read",
    description="Mark a specific notification as read.",
)
async def mark_as_read(
    notification_id: int,
    service: NotificationsService = Depends(get_notifications_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Mark a single notification read."""
    notif = await service.mark_single_read(notification_id)
    if notif is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"success": True, "data": NotificationResponse.model_validate(notif)}
