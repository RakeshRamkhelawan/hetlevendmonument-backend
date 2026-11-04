"""Management logs router: system logs and broadcast queue."""

import logging
from typing import Any

from fastapi import APIRouter, Depends

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user, require_scopes, OAuth2Scope

from src.core.api.management_endpoints import log_broadcast_queue, log_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["management"])


@router.get("/logs")
async def get_logs(
    limit: int = 50,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, list[Any]]:  # TODO(TYPE): replace Any with concrete type
    """Get recent system logs. Requires: Permission.READ"""
    logger.info("User %s requesting logs (limit=%s)", current_user.id, limit)
    return {"logs": log_entries[-limit:]}


@router.get("/logs/broadcast-queue")
async def get_log_broadcast_queue(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, list[Any]]:  # TODO(TYPE): replace Any with concrete type
    """Get logs for WebSocket broadcast. Requires: Permission.READ"""
    logger.info("User %s requesting log broadcast queue", current_user.id)
    return {"queue": log_broadcast_queue}
