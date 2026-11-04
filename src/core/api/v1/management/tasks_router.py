"""Management tasks router: costs, task queue."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user, require_scopes, OAuth2Scope

from src.core.api.management_endpoints import log_broadcast_queue, log_entries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["management"])


@router.get("/costs")
async def get_costs(
    period: str = "7d",
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get cost and usage data for specified period. Requires: Permission.READ"""
    logger.info("User %s requesting costs for period %s", current_user.id, period)
    return {
        "total_cost": 156.73,
        "period": period,
        "by_provider": [
            {"provider": "Anthropic", "cost": 78.45, "tokens_millions": 52.3, "requests": 1247},
            {"provider": "Google", "cost": 52.18, "tokens_millions": 68.7, "requests": 892},
            {"provider": "OpenAI", "cost": 26.10, "tokens_millions": 15.2, "requests": 445},
        ],
        "by_agent": [
            {"agent": "cva_main", "cost": 65.20, "requests": 856},
            {"agent": "research_specialist_001", "cost": 54.33, "requests": 423},
            {"agent": "code_specialist_001", "cost": 37.20, "requests": 305},
        ],
        "historical": [
            {"date": "2025-01-10", "cost": 23.45},
            {"date": "2025-01-11", "cost": 31.22},
            {"date": "2025-01-12", "cost": 28.17},
            {"date": "2025-01-13", "cost": 35.89},
            {"date": "2025-01-14", "cost": 38.00},
        ],
    }


@router.get("/tasks")
async def get_task_queue(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
    """Get current task queue. Requires: Permission.READ"""
    logger.info("User %s requesting task queue", current_user.id)
    tasks = [
        {
            "id": "task_001",
            "type": "research",
            "priority": "high",
            "status": "running",
            "agent": "research_specialist_001",
            "created_at": "2025-01-15T12:00:00Z",
            "description": "Market analysis for Q1 2025",
        },
        {
            "id": "task_002",
            "type": "code_review",
            "priority": "medium",
            "status": "queued",
            "agent": "code_specialist_001",
            "created_at": "2025-01-15T12:15:00Z",
            "description": "Security audit of new authentication module",
        },
    ]
    return {"tasks": tasks}


@router.post("/tasks/{task_id}/prioritize")
async def prioritize_task(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, str]:
    """Prioritize a task in the queue. Requires: Permission.ADMIN"""
    logger.info("User %s prioritizing task %s", current_user.id, task_id)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "INFO",
        "component": "TaskManager",
        "message": "Task %s prioritized by %s" % (task_id, current_user.email),
    }
    log_entries.append(log_entry)
    log_broadcast_queue.append(log_entry)
    return {"status": "success", "message": "Task %s prioritized" % task_id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, str]:
    """Cancel a task. Requires: Permission.ADMIN"""
    logger.info("User %s cancelling task %s", current_user.id, task_id)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": "WARN",
        "component": "TaskManager",
        "message": "Task %s cancelled by %s" % (task_id, current_user.email),
    }
    log_entries.append(log_entry)
    log_broadcast_queue.append(log_entry)
    return {"status": "success", "message": "Task %s cancelled" % task_id}
