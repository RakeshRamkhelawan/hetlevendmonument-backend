# orphan:exempt r1 -- subagents execution endpoints, no tenant-scoped ORM data
"""Subagents action execution and status query endpoints."""

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

from .dependencies import SubagentLoader, get_subagent_loader
from .schemas import AgentActionRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Subagents"])


@router.post("/action")
async def execute_agent_action(
    request: AgentActionRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute an action on an active agent."""
    try:
        agent = loader.get_agent(request.agent_name)
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Active agent {request.agent_name} not found",
            )

        if request.action == "execute":
            if not hasattr(agent, "execute"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Agent {request.agent_name} does not support execute action",
                )
            if asyncio.iscoroutinefunction(agent.execute):
                result = await agent.execute(**request.parameters)
            else:
                result = agent.execute(**request.parameters)
            return {"success": True, "result": result}

        if request.action == "status":
            if hasattr(agent, "get_status"):
                if asyncio.iscoroutinefunction(agent.get_status):
                    agent_status = await agent.get_status()
                else:
                    agent_status = agent.get_status()
                return {"success": True, "status": agent_status}
            return {"success": True, "status": "active"}

        if request.action == "capabilities":
            if hasattr(agent, "get_capabilities"):
                if asyncio.iscoroutinefunction(agent.get_capabilities):
                    capabilities = await agent.get_capabilities()
                else:
                    capabilities = agent.get_capabilities()
                return {"success": True, "capabilities": capabilities}
            agent_def = loader.agents[request.agent_name]
            return {"success": True, "capabilities": agent_def.capabilities}

        # Custom method dispatch
        if hasattr(agent, request.action):
            method = getattr(agent, request.action)
            if callable(method):
                if asyncio.iscoroutinefunction(method):
                    result = await method(**request.parameters)
                else:
                    result = method(**request.parameters)
                return {"success": True, "result": result}

        raise HTTPException(
            status_code=400,
            detail=f"Action {request.action} not supported by agent {request.agent_name}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "execute_agent_action failed action=%s agent=%s: %s: %s",
            request.action,
            request.agent_name,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Action execution failed") from e


@router.get("/status/{agent_name}")
async def get_agent_status(
    agent_name: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return detailed status information for the specified agent."""
    try:
        if agent_name not in loader.agents:
            raise HTTPException(status_code=404, detail=f"Agent {agent_name} not found")
        agent_def = loader.agents[agent_name]
        instance = loader.get_agent(agent_name)
        instance_info = None
        if instance:
            instance_info = {
                "type": type(instance).__name__,
                "has_execute": hasattr(instance, "execute"),
                "has_status": hasattr(instance, "get_status"),
                "methods": [m for m in dir(instance) if not m.startswith("_")],
            }
        return {
            "name": agent_def.name,
            "type": agent_def.agent_type,
            "status": agent_def.status.value,
            "description": agent_def.description,
            "capabilities": agent_def.capabilities,
            "dependencies": agent_def.dependencies,
            "priority": agent_def.priority,
            "module_path": agent_def.module_path,
            "class_name": agent_def.class_name,
            "load_error": agent_def.load_error,
            "instance_info": instance_info,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "get_agent_status failed for %s: %s: %s", agent_name, type(e).__name__, e, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Status check failed") from e


@router.get("/types/{agent_type}")
async def get_agents_by_type(
    agent_type: str,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    loader: SubagentLoader = Depends(get_subagent_loader),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return information about all agents matching the specified type."""
    try:
        matching_agents = [a for a in loader.list_available_agents() if a["type"] == agent_type]
        active_instances = loader.get_agents_by_type(agent_type)
        return {
            "agent_type": agent_type,
            "total_agents": len(matching_agents),
            "active_instances": len(active_instances),
            "agents": matching_agents,
            "active_agent_names": [
                name
                for name, _agent in loader.active_agents.items()
                if loader.agents[name].agent_type == agent_type
            ],
        }
    except Exception as e:
        logger.error(
            "get_agents_by_type failed for %s: %s: %s",
            agent_type,
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Type query failed") from e
