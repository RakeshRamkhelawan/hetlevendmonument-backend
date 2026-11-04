# orphan:exempt r1 -- subagents discovery endpoints, no tenant-scoped ORM data
"""Subagents discovery and monitoring endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
    OAuth2Scope,
)

from .dependencies import AgentStatus, SubagentLoader, get_subagent_loader
from .schemas import AgentInfo, AgentListResponse, LoaderMetrics

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Subagents"])


def _build_agent_list(loader: SubagentLoader) -> tuple[list[AgentInfo], dict[str, int]]:
    """Build AgentInfo list and status summary from loader state."""
    agent_list = loader.list_available_agents()
    agents = [
        AgentInfo(
            name=cast(str, a["name"]),
            type=cast(str, a["type"]),
            status=cast(str, a["status"]),
            description=cast(str, a["description"]),
            capabilities=cast(list[str], a["capabilities"]),
            priority=cast(int, a["priority"]),
            error=cast(Optional[str], a["error"]),
        )
        for a in agent_list
    ]
    status_summary: dict[str, int] = {
        s.value: sum(1 for a in agent_list if a["status"] == s.value) for s in AgentStatus
    }
    return agents, status_summary


@router.get("/discover", response_model=AgentListResponse)
async def discover_agents(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> AgentListResponse:
    """Discover all available subagents and return their metadata (paginated)."""
    try:
        await loader.discover_agents()
        agents, status_summary = _build_agent_list(loader)
        paginated = agents[offset : offset + limit]
        return AgentListResponse(
            total_agents=len(agents), agents=paginated, status_summary=status_summary
        )
    except Exception as e:
        logger.error("discover_agents failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Discovery failed") from e


@router.get("/list", response_model=AgentListResponse)
async def list_agents(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> AgentListResponse:
    """List all known agents with their current status (paginated)."""
    try:
        agents, status_summary = _build_agent_list(loader)
        paginated = agents[offset : offset + limit]
        return AgentListResponse(
            total_agents=len(agents), agents=paginated, status_summary=status_summary
        )
    except Exception as e:
        logger.error("list_agents failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Listing failed") from e


@router.get("/metrics", response_model=LoaderMetrics)
async def get_loader_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> LoaderMetrics:
    """Return comprehensive metrics about the loader and agent states."""
    try:
        metrics = loader.get_metrics()
        return LoaderMetrics(
            total_agents=cast(int, metrics["total_agents"]),
            loaded_agents=cast(int, metrics["loaded_agents"]),
            active_agents=cast(int, metrics["active_agents"]),
            status_distribution=cast(dict[str, int], metrics["status_distribution"]),
            agent_types=cast(list[str], metrics["agent_types"]),
            loaded_modules=cast(int, metrics["loaded_modules"]),
        )
    except Exception as e:
        logger.error("get_loader_metrics failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Metrics retrieval failed") from e


@router.get("/health")
async def subagent_health(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return current health status of the subagent management system."""
    try:
        metrics = loader.get_metrics()
        health_status = "healthy"
        if metrics["active_agents"] == 0:
            health_status = "warning"
        failed = cast(dict[str, int], metrics["status_distribution"]).get("error", 0)
        if failed > 0:
            total = cast(int, metrics["total_agents"])
            health_status = "degraded" if failed < total / 2 else "unhealthy"
        return {
            "status": health_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics,
            "message": (
                f"Subagent system operational with {metrics['active_agents']} active agents"
            ),
        }
    except Exception as e:
        logger.error("subagent_health failed: %s: %s", type(e).__name__, e, exc_info=True)
        return {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": "Er is een fout opgetreden.",
            "message": "Subagent health check failed",
        }
