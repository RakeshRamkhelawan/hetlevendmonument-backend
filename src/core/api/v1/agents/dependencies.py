"""
Agent domain shared dependencies (ADR-033 Laag 1 re-exports).

Router bestanden mogen src.core.database, src.core.agents, src.core.auth etc.
NIET direct importeren. Alle benodigde dependencies worden hier gebundeld
zodat sub-routers deze module als enige source gebruiken.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.core.agents.agent_registry import AgentRegistry as AgentRegistry  # noqa: F401 re-export
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope
from src.core.database.database import get_db


async def get_agent_registry_dependency(
    session: AsyncSession = Depends(get_db),
) -> "AgentRegistry":
    """Provide a request-scoped AgentRegistry bound to the active DB session."""
    from src.core.agents.agent_registry import AgentRegistry

    return AgentRegistry(session)


async def get_agent_registry_repository_dependency(
    session: AsyncSession = Depends(get_db),
) -> "AgentRegistryRepository":
    """Provide a request-scoped AgentRegistryRepository bound to the active DB session."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    return AgentRegistryRepository(session)


if TYPE_CHECKING:
    from src.core.copilot.council.coordinator import AgentCouncil as AgentCouncil  # noqa: F401


async def get_council_dependency(
    session: AsyncSession = Depends(get_db),
) -> "AgentCouncil":
    """Provide a request-scoped AgentCouncil for the governance gate (RC-001)."""
    from src.core.copilot.council.factory import build_council

    return await build_council(session)


async def agent_execute_limit_dep(
    http_request: Request,
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> None:
    """Rate-limit dependency: 10 agent executes/min per tenant+user (RC-009a)."""
    from src.core.governance.rate_limiter import check_agent_execute_limit

    await check_agent_execute_limit(current_user.tenant_id, current_user.id)


async def require_agent_council_approval(
    council: "AgentCouncil",
    tenant_id: int,
    user_id: int,
    action_type: str,
    action_params: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    reasoning: str,
    db: AsyncSession,
) -> None:
    """Enforce council governance gate for agent actions (ADR-033 facade).

    `db` (ADR-036 OP-167, sprint dag 2): doorgegeven aan `require_council_approval` zodat
    een HITL_REQUIRED-verdict daadwerkelijk een goedkeuringsticket krijgt in plaats van
    stilzwijgend te verdwijnen (net als BLOCKED/MODIFIED/DEFERRED, maar dat verdict hoort
    een mens te kunnen zien en goedkeuren, AI Act art. 14).
    """
    from src.core.copilot.council.governance_gate import require_council_approval

    await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=user_id,
        action_type=action_type,
        action_params=action_params,
        reasoning=reasoning,
        db=db,
    )


__all__ = [
    "AgentRegistry",
    "AgentRegistryRepository",
    "AgentCouncil",
    "get_db",
    "get_current_user_dependency",
    "get_agent_registry_dependency",
    "get_agent_registry_repository_dependency",
    "get_council_dependency",
    "agent_execute_limit_dep",
    "require_agent_council_approval",
    "require_scopes",
    "OAuth2Scope",
    "AsyncSession",
    "UserResponse",
    "Depends",
    "Request",
]
