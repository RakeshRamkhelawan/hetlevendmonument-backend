# orphan:exempt r1 -- subagents management endpoints, no tenant-scoped ORM data
"""Subagents load and lifecycle management endpoints."""

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
    OAuth2Scope,
)

from .dependencies import AgentStatus, SubagentLoader, get_subagent_loader
from .schemas import AgentInstantiateRequest, AgentLoadRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Subagents"])


@router.post("/load")
async def load_agents(
    request: AgentLoadRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Load specific agents by name, respecting force_reload flag."""
    try:
        results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for agent_name in request.agent_names:
            if request.force_reload:
                success = await loader.reload_agent(agent_name)
            else:
                success = await loader.load_agent(agent_name)
            agent_status = loader.get_agent_status(agent_name)
            results[agent_name] = {
                "success": success,
                "status": agent_status.value if agent_status is not None else "unknown",
            }
        return {
            "message": f"Processed {len(request.agent_names)} agents",
            "results": results,
            "total_loaded": sum(1 for r in results.values() if r["success"]),
        }
    except Exception as e:
        logger.error("load_agents failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Loading failed") from e


@router.post("/instantiate")
async def instantiate_agent(
    request: AgentInstantiateRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Instantiate a loaded agent with the given configuration."""
    try:
        status = loader.get_agent_status(request.agent_name)
        if not status or status == AgentStatus.UNLOADED:
            raise HTTPException(
                status_code=400,
                detail=f"Agent {request.agent_name} is not loaded. Load it first.",
            )
        instance = await loader.instantiate_agent(request.agent_name, **request.config)
        if not instance:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to instantiate agent {request.agent_name}",
            )
        return {
            "message": f"Agent {request.agent_name} instantiated successfully",
            "agent_name": request.agent_name,
            "status": "active",
            "instance_type": type(instance).__name__,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "instantiate_agent failed for %s: %s: %s",
            request.agent_name,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Instantiation failed") from e


@router.post("/load-all")
async def load_all_agents(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Discover and load all available agents in priority order."""
    try:
        await loader.discover_agents()
        results = await loader.load_all_agents()
        successful_loads = sum(1 for success in results.values() if success)
        return {
            "message": f"Loaded {successful_loads} out of {len(results)} agents",
            "results": results,
            "total_agents": len(results),
            "successful_loads": successful_loads,
            "failed_loads": len(results) - successful_loads,
        }
    except Exception as e:
        logger.error("load_all_agents failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Bulk loading failed") from e


@router.delete("/unload/{agent_name}")
async def unload_agent(
    agent_name: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Stop and remove the specified agent from active memory."""
    try:
        if agent_name not in loader.agents:
            raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
        if agent_name in loader.active_agents:
            agent = loader.active_agents[agent_name]
            stop_fn = getattr(agent, "stop", None)
            if stop_fn is not None:
                if asyncio.iscoroutinefunction(stop_fn):
                    await stop_fn()
                else:
                    stop_fn()
            del loader.active_agents[agent_name]
        agent_def = loader.agents[agent_name]
        agent_def.status = AgentStatus.UNLOADED
        agent_def.instance = None
        agent_def.load_error = None
        return {
            "message": f"Agent {agent_name} unloaded successfully",
            "agent_name": agent_name,
            "status": "unloaded",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "unload_agent failed for %s: %s: %s", agent_name, type(e).__name__, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Unload failed") from e
