# orphan:exempt r1 -- subagents management endpoints, no tenant-scoped ORM data
"""Subagents management router (ADR-033 Laag 1 composiet)."""

from fastapi import APIRouter

from src.core.auth.api_deps import get_current_user_dependency as get_current_user, require_scopes  # noqa: F401 (patched in tests)

from .dependencies import AgentStatus, get_subagent_loader  # noqa: F401 (patched in tests)
from .router_discovery import discover_agents, list_agents  # noqa: F401 (re-export for legacy shim)
from .router_discovery import router as discovery_router
from .router_execution import get_agent_status  # noqa: F401 (re-export for legacy shim)
from .router_execution import router as execution_router
from .router_management import instantiate_agent, load_agents  # noqa: F401 (re-export for legacy shim)
from .router_management import router as management_router

__all__ = [
    "router",
    "discover_agents",
    "list_agents",
    "get_agent_status",
    "instantiate_agent",
    "load_agents",
]

router = APIRouter(prefix="/api/v1/subagents", tags=["Subagents"])
router.include_router(discovery_router)
router.include_router(management_router)
router.include_router(execution_router)
