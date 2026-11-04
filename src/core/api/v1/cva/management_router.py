# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""CVA management endpoints -- status, health, optimize, analytics, shutdown (ADR-033 Laag 1)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from src.core.api.v1.cva.dependencies import probe_llm_health
from src.core.api.v1.cva.state import _cva_agents, get_cva_agent
from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    get_optional_user_dependency as get_optional_user,
    require_scopes,
    OAuth2Scope,
)


logger = logging.getLogger(__name__)

management_router = APIRouter(prefix="/api/v1/cva", tags=["cva"])


class CVAStatusResponse(BaseModel):
    """Response model for CVA status."""

    agent_id: str
    mode: str
    active: bool
    capabilities: dict[str, bool]
    performance_metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    execution_history_size: int
    last_optimization: str


@management_router.get("/status", response_model=CVAStatusResponse)
async def get_cva_status(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> CVAStatusResponse:
    """Get Ultimate CVA Agent status. Requires: AGENTS_READ"""
    try:
        logger.info("User %s requesting CVA status", current_user.id)
        cva_agent = await get_cva_agent(tenant_id=current_user.tenant_id)

        return CVAStatusResponse(
            agent_id=getattr(cva_agent, "agent_id", "unknown"),
            mode=getattr(cva_agent, "cva_mode", "unknown"),
            active=getattr(cva_agent, "learning_enabled", False),
            capabilities=getattr(cva_agent, "capabilities", {}),
            performance_metrics=getattr(cva_agent, "_get_performance_metrics", lambda: {})(),
            execution_history_size=len(getattr(cva_agent, "execution_history", [])),
            last_optimization=getattr(
                cva_agent, "last_optimization", datetime.now(timezone.utc)
            ).isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("CVA status error: %s", e)
        raise HTTPException(status_code=500, detail="CVA status retrieval failed")


@management_router.get("/health", response_model=dict[str, Any])
async def get_cva_health(
    request: Request,
    current_user: UserResponse | None = Depends(get_optional_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Check the health of the CVA service.

    States:
    - healthy: Service is up, authenticated, and providers are ready.
    - unauthorized: User is not logged in.
    - provider_error: User is logged in but no LLM providers are available.
    - initializing: Service is still booting up.
    - error: Generic system error.
    """
    try:
        if current_user is None:
            return {
                "service": "cva",
                "status": "unauthorized",
                "healthy": False,
                "error": "Authentication required",
                "authenticated": False,
            }

        if os.getenv("LLM_PROVIDER", "").lower() == "mock":
            return {
                "service": "cva",
                "status": "healthy",
                "healthy": True,
                "mode": "mock",
                "authenticated": True,
            }

        probe_result = await probe_llm_health()
        if probe_result.get("config_error"):
            logger.warning("LLM not configured (env vars missing): %s", probe_result.get("message"))
            return {
                "service": "cva",
                "status": "healthy",
                "healthy": True,
                "warning": "LLM env vars not configured. Set LLM_PROVIDER and LLM_MODEL.",
                "authenticated": True,
            }
        elif not probe_result["available"]:
            logger.warning(
                "LLM provider unavailable during health check: %s", probe_result.get("message")
            )
            return {
                "service": "cva",
                "status": "provider_error",
                "healthy": False,
                "error": "LLM provider failed to initialize. Check provider credentials.",
                "authenticated": True,
            }

        return {
            "service": "cva",
            "status": "healthy",
            "healthy": True,
            "authenticated": True,
            "active_providers": [probe_result["provider"]],
            "default_provider": os.getenv("LLM_PROVIDER", "ollama"),
        }

    except Exception as e:
        logger.error("CVA health check critical error: %s", e)
        return {"service": "cva", "status": "error", "healthy": False, "error": "Internal error"}


@management_router.get("/status-detail")
async def get_cva_status_detail(
    request: Request,
    current_user: UserResponse | None = Depends(get_optional_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Alias for health with more detail."""
    return await get_cva_health(request, current_user)


@management_router.post("/optimize")
async def optimize_cva(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Trigger CVA system optimization. Requires: ADMIN_ALL"""
    try:
        logger.info("User %s triggering CVA optimization", current_user.id)
        cva_agent = await get_cva_agent(tenant_id=current_user.tenant_id)

        optimizer = getattr(cva_agent, "_optimize_system_configuration", None)
        if callable(optimizer):
            optimizer()

        return {
            "message": "CVA optimization completed",
            "timestamp": getattr(
                cva_agent, "last_optimization", datetime.now(timezone.utc)
            ).isoformat(),
            "performance_metrics": getattr(cva_agent, "_get_performance_metrics", lambda: {})(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("CVA optimization error: %s", e)
        raise HTTPException(status_code=500, detail="CVA optimization failed")


@management_router.get("/analytics")
async def get_cva_analytics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get CVA performance analytics. Requires: AGENTS_READ"""
    try:
        logger.info("User %s requesting CVA analytics", current_user.id)
        cva_agent = await get_cva_agent(tenant_id=current_user.tenant_id)

        total_commands = len(cva_agent.execution_history)
        successful_commands = len([ex for ex in cva_agent.execution_history if ex.success])

        analytics = {
            "total_commands_processed": total_commands,
            "success_rate": (successful_commands / max(total_commands, 1)) * 100,
            "average_execution_time": sum(ex.execution_time for ex in cva_agent.execution_history)
            / max(total_commands, 1),
            "average_confidence": sum(ex.confidence for ex in cva_agent.execution_history)
            / max(total_commands, 1),
            "llm_providers_used": list(
                {ex.llm_provider_used for ex in cva_agent.execution_history if ex.llm_provider_used}
            ),
            "orchestration_usage_rate": (
                len([ex for ex in cva_agent.execution_history if ex.orchestration_used])
                / max(total_commands, 1)
            )
            * 100,
            "learning_enabled": cva_agent.learning_enabled,
            "context_memory_size": len(cva_agent.context_memory),
            "performance_cache_size": len(cva_agent.performance_cache),
            "capabilities_active": sum(
                1 for capability in cva_agent.capabilities.__dict__.values() if capability
            ),
        }

        return {
            "analytics": analytics,
            "timestamp": cva_agent.last_optimization.isoformat(),
            "agent_mode": cva_agent.cva_mode.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("CVA analytics error: %s", e)
        raise HTTPException(status_code=500, detail="CVA analytics retrieval failed")


@management_router.post("/shutdown")
async def shutdown_cva(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Gracefully shutdown CVA agent. Requires: ADMIN_ALL"""
    try:
        logger.info("User %s shutting down CVA agent", current_user.id)
        for _, agent in list(_cva_agents.items()):
            shutdown_fn = getattr(agent, "shutdown", None)
            if callable(shutdown_fn):
                shutdown_fn()
        _cva_agents.clear()

        return {
            "message": "CVA agent shutdown completed",
            "timestamp": str(datetime.now(timezone.utc)),
        }

    except Exception as e:
        logger.exception("CVA shutdown error: %s", e)
        raise HTTPException(status_code=500, detail="CVA shutdown failed")
