"""Management agents router: agent status, pause, resume, restart."""

import logging
from typing import Any, NoReturn

from fastapi import APIRouter, Depends, status

from src.core.auth.api_deps import (
    OAuth2Scope,
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
)
from src.core.api.agent_control_unavailable import (
    UNAVAILABLE_RESPONSES,
    refuse_agent_control,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["management"])


@router.get("/agents")
async def get_agents_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
    """Get all agents status. Requires: Permission.READ"""
    logger.info("User %s requesting agents status", current_user.id)
    agents = [
        {
            "agent_id": "cva_main",
            "type": "CVA",
            "status": "healthy",
            "load": 0.35,
            "tasks_completed": 127,
            "avg_response_time": 2.1,
        },
        {
            "agent_id": "research_specialist_001",
            "type": "Specialist",
            "status": "busy",
            "load": 0.78,
            "tasks_completed": 45,
            "avg_response_time": 5.2,
        },
        {
            "agent_id": "code_specialist_001",
            "type": "Specialist",
            "status": "healthy",
            "load": 0.42,
            "tasks_completed": 33,
            "avg_response_time": 3.8,
        },
    ]
    return {"agents": agents}


# NOTE: pause/resume/restart weigeren expliciet met 501. Zie
# `src/core/api/agent_control_unavailable.py` voor de meting waarom de bestaande
# AgentCircuitBreaker hier geen bruikbaar hold-primitief is, en
# `tests/unit/api/test_pause_agent_pauses_or_fails_loud.py` voor de poort erop.
@router.post(
    "/agents/{agent_id}/pause",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=None,
    responses=UNAVAILABLE_RESPONSES,
)
async def pause_agent(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> NoReturn:
    """Pause an agent. Requires: Permission.ADMIN. Not implemented -- refuses with 501."""
    logger.info("User %s pausing agent %s", current_user.id, agent_id)
    refuse_agent_control("pause", agent_id, str(current_user.id))


@router.post(
    "/agents/{agent_id}/resume",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=None,
    responses=UNAVAILABLE_RESPONSES,
)
async def resume_agent(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> NoReturn:
    """Resume an agent. Requires: Permission.ADMIN. Not implemented -- refuses with 501."""
    logger.info("User %s resuming agent %s", current_user.id, agent_id)
    refuse_agent_control("resume", agent_id, str(current_user.id))


@router.post(
    "/agents/{agent_id}/restart",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    response_model=None,
    responses=UNAVAILABLE_RESPONSES,
)
async def restart_agent(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> NoReturn:
    """Restart an agent. Requires: Permission.ADMIN. Not implemented -- refuses with 501."""
    logger.info("User %s restarting agent %s", current_user.id, agent_id)
    refuse_agent_control("restart", agent_id, str(current_user.id))
