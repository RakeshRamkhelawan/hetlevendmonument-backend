"""External Agent API Router

Endpoints for external agent management and heartbeat protocol.

Authentication:
- Register/List/Delete: JWT (tenant admin)
- Heartbeat/Task/Complete: API key (Bearer token)
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status

from src.core.api.v1.company.feature_flags_dependency import require_company_layer_enabled
from src.core.auth.api_deps import get_current_user
from src.core.company.external_agent_service import ExternalAgentService
from src.core.company.schemas import (
    ExternalAgentRegister,
    HeartbeatRequest,
    TaskCompleteRequest,
)
from src.core.container import TenantContext, container
from src.core.api.v1.company.dependencies import DatabaseManager, get_external_agent_tenant_id
from src.core.exceptions.exceptions import AuthError, NotFoundError
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)


class _NullPolicyEngine:
    """Null-object fallback for policy_engine when not wired in container."""

    def validate_output(
        self,
        x: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, bool]:  # TODO(TYPE): replace Any with concrete type
        return {"valid": True}


@dataclass
class _NullBudgetResult:
    """Sentinel return value for _NullBudgetManager -- mirrors BudgetCheckResult interface."""

    allowed: bool = True
    remaining_tokens: int = 10_000_000
    remaining_cost: Decimal = field(default_factory=lambda: Decimal("9999.99"))
    current_usage_tokens: int = 0
    current_usage_cost: Decimal = field(default_factory=lambda: Decimal("0.00"))
    reason: str | None = None
    alert_triggered: bool = False


class _NullBudgetManager:
    """Null-object fallback for budget_manager when not wired in container."""

    def __init__(self) -> None:
        self.tracked_usages: list[dict[str, object]] = []

    async def check_budget(self, *args: Any, **kwargs: Any) -> _NullBudgetResult:
        return _NullBudgetResult()

    async def track_usage(self, *args: Any, **kwargs: Any) -> None:
        self.tracked_usages.append({"args": args, "kwargs": kwargs})


router = APIRouter(
    prefix="/agents",
    tags=["external-agents"],
    dependencies=[Depends(require_company_layer_enabled)],
)


def get_external_agent_service(
    current_user: User = Depends(get_current_user),
) -> ExternalAgentService:
    """Get external agent service with tenant context."""
    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )

    policy_engine = getattr(container, "policy_engine", None)
    if policy_engine is None:
        logger.warning(
            "policy_engine not wired in container; using _NullPolicyEngine (no policy enforcement)"
        )
        policy_engine = _NullPolicyEngine()

    budget_manager = getattr(container, "budget_manager", None)
    if budget_manager is None:
        logger.warning(
            "budget_manager not wired in container; using _NullBudgetManager (no budget enforcement)"
        )
        budget_manager = _NullBudgetManager()

    db_manager = container.database_manager()
    if db_manager is None:
        raise RuntimeError("Database manager not initialized")

    return ExternalAgentService(
        db_manager=cast(DatabaseManager, db_manager),
        tenant_context=tenant_context,
        policy_engine=policy_engine,
        budget_manager=budget_manager,
    )


async def get_agent_from_api_key(
    x_api_key: str | None = Header(None),
) -> tuple[UUID, str]:
    """Extract and parse agent ID from X-API-Key header.

    NOTE: only parses the header -- bcrypt verification happens in each service call.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )

    # API key format: agent_id:api_key
    if ":" not in x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Expected: agent_id:api_key",
        )

    try:
        agent_id_str, api_key = x_api_key.split(":", 1)
        agent_id = UUID(agent_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid agent ID in API key",
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing credential segment after agent identifier",
        )

    return agent_id, api_key


async def get_agent_service_from_api_key(
    credentials: tuple[UUID, str] = Depends(get_agent_from_api_key),
) -> ExternalAgentService:
    """Get ExternalAgentService with tenant resolved via agent DB lookup.

    Used by API-key authenticated endpoints -- no JWT required.
    Tenant context is derived from the agent record in the database.
    NOTE: this only resolves tenant_id for context construction. The bcrypt
    verification of the credential always happens inside the service call itself.
    """
    agent_uuid, _ = credentials
    db_manager = container.database_manager()
    if db_manager is None:
        raise RuntimeError("Database manager not initialized")
    cast_db = cast(DatabaseManager, db_manager)

    resolved_tenant_id = await get_external_agent_tenant_id(cast_db, agent_uuid)
    if resolved_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    tenant_ctx = TenantContext(
        tenant_id=resolved_tenant_id,
        tenant_slug=None,
        bypass_filter=False,
    )

    policy_engine = getattr(container, "policy_engine", None)
    if policy_engine is None:
        policy_engine = _NullPolicyEngine()
    budget_manager = getattr(container, "budget_manager", None)
    if budget_manager is None:
        budget_manager = _NullBudgetManager()

    return ExternalAgentService(
        db_manager=cast_db,
        tenant_context=tenant_ctx,
        policy_engine=policy_engine,
        budget_manager=budget_manager,
    )


# =============================================================================
# Admin Endpoints (JWT Auth)
# =============================================================================


@router.post(
    "/external/register",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    status_code=status.HTTP_201_CREATED,
    summary="Register new external agent",
)
async def register_agent(
    data: ExternalAgentRegister,
    service: ExternalAgentService = Depends(get_external_agent_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Register a new external agent.

    Returns agent_id, api_key (shown once), and heartbeat_endpoint.
    """
    try:
        result = await service.register(data)
        return {"success": True, "data": result}
    except ValueError as e:
        logger.error("register_agent mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ongeldig verzoek.",
        )


@router.get(
    "/external",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="List all external agents",
)
async def list_agents(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: ExternalAgentService = Depends(get_external_agent_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all external agents for the tenant."""
    result = await service.list_agents(limit=limit, offset=offset)
    return {"success": True, "data": [agent.model_dump() for agent in result]}


@router.delete(
    "/external/{agent_id}",
    status_code=status.HTTP_200_OK,
    summary="Deregister external agent",
    response_class=Response,
)
async def deregister_agent(
    agent_id: UUID,
    service: ExternalAgentService = Depends(get_external_agent_service),
) -> None:
    """Deregister an external agent (soft delete)."""
    try:
        await service.deregister(agent_id)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# =============================================================================
# Agent Endpoints (API Key Auth)
# =============================================================================


@router.post(
    "/{agent_id}/heartbeat",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Send heartbeat",
)
async def heartbeat(
    agent_id: UUID,
    data: HeartbeatRequest,
    credentials: tuple[UUID, str] = Depends(get_agent_from_api_key),
    service: ExternalAgentService = Depends(get_agent_service_from_api_key),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Send heartbeat to update status and receive pending tasks.

    Authentication: X-API-Key header with format: agent_id:api_key
    """
    _, extracted_api_key = credentials
    try:
        result = await service.heartbeat(agent_id, extracted_api_key, data)
        return {"success": True, "data": result.model_dump()}
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{agent_id}/tasks/next",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Get next pending task",
)
async def get_next_task(
    agent_id: UUID,
    credentials: tuple[UUID, str] = Depends(get_agent_from_api_key),
    service: ExternalAgentService = Depends(get_agent_service_from_api_key),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get the next pending task assigned to this agent.

    Authentication: X-API-Key header with format: agent_id:api_key
    """
    cred_agent_id, extracted_api_key = credentials

    # Verify agent is accessing its own tasks
    if cred_agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only access own tasks",
        )

    try:
        task = await service.get_next_task(agent_id, extracted_api_key)
        return {"success": True, "data": task.model_dump(mode="json") if task is not None else None}
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post(
    "/{agent_id}/tasks/{task_id}/complete",
    status_code=status.HTTP_200_OK,
    summary="Complete task",
    response_class=Response,
)
async def complete_task(
    agent_id: UUID,
    task_id: UUID,
    data: TaskCompleteRequest,
    credentials: tuple[UUID, str] = Depends(get_agent_from_api_key),
    service: ExternalAgentService = Depends(get_agent_service_from_api_key),
) -> None:
    """Mark task as completed.

    Authentication: X-API-Key header with format: agent_id:api_key
    """
    cred_agent_id, extracted_api_key = credentials

    # Verify agent is completing its own task
    if cred_agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only complete own tasks",
        )

    try:
        await service.complete_task(agent_id, task_id, data, extracted_api_key)
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except AuthError as e:
        # AuthError.status_code distinguishes auth failure (401) from ownership
        # mismatch (403) -- see ExternalAgentService.complete_task
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
        )
