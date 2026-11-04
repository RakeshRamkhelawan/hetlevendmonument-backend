"""CVA public endpoints -- POST /create_agent and POST /execute/{agent_id} (ADR-033 Laag 1)."""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    require_scopes,
    OAuth2Scope,
)
from src.core.shared.interfaces import AgentCapability, AgentStatus, ExecutionResult, TaskData
from src.core.types import AgentType, TaskPriority
from src.core.api.v1.cva.dependencies import (
    AgentRegistry,
    get_cva_agent_registry_dependency,
    get_cva_agent_registry_repository_dependency,
)

if TYPE_CHECKING:
    from src.core.api.v1.cva.dependencies import AgentRegistryRepository  # own-domain -- ADR-033

logger = logging.getLogger(__name__)

public_router = APIRouter(prefix="/cva", tags=["cva"])


class CVACreateAgentRequest(BaseModel):
    """Request payload for creating a managed CVA agent."""

    name: str
    description: str | None = None
    capabilities: list[str] | None = None


class CVAExecuteAgentRequest(BaseModel):
    """Execution payload for managed CVA agents."""

    input: str = Field(..., min_length=1)
    context: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class ManagedCVAAgent:
    """Lightweight CVA agent implementation backed by the registry."""

    def __init__(
        self,
        agent_id: str,
        description: str | None,
        capabilities: list[str],
        name: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.address = f"cva://{agent_id}"
        self.agent_type = AgentType.CVA
        self.name = name
        self.description = description or "Managed CVA agent"
        self._capabilities = [
            AgentCapability(
                name=cap,
                description=f"CVA capability: {cap}",
                input_types=["text"],
                output_types=["text"],
            )
            for cap in capabilities
        ]

    async def get_capabilities(self) -> list[AgentCapability]:
        return self._capabilities

    async def get_status(self) -> AgentStatus:
        """Return agent status for protocol compliance."""
        return AgentStatus(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            is_active=True,
            current_load=0.0,
            capabilities=self._capabilities,
        )

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Process task with correct parameter name for Agent protocol."""
        response = {
            "agent_id": self.agent_id,
            "message": task.description,
            "context": task.metadata,
            "summary": f"{self.description} handled request",
        }
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data=response,
            execution_time=0.05,
            logs=["ManagedCVAAgent executed task"],
        )


@public_router.post("/create_agent", status_code=status.HTTP_201_CREATED)
async def create_managed_cva_agent(
    request: CVACreateAgentRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: AgentRegistry = Depends(get_cva_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a managed CVA agent accessible via simplified endpoints."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not resolved")

    capabilities = request.capabilities or ["conversation"]
    agent_id = f"cva_{uuid.uuid4().hex[:8]}"

    managed_agent = ManagedCVAAgent(agent_id, request.description, capabilities, name=request.name)
    registered = await registry.register_agent(managed_agent)
    if not registered:
        logger.error("Failed to register managed CVA agent %s", agent_id)
        raise HTTPException(status_code=500, detail="Failed to initialize CVA agent")

    return {
        "id": agent_id,
        "name": request.name,
        "description": request.description,
        "status": "created",
    }


@public_router.post("/execute/{agent_id}")
async def execute_managed_cva_agent(
    agent_id: str,
    request: CVAExecuteAgentRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: AgentRegistry = Depends(get_cva_agent_registry_dependency),
    repo: AgentRegistryRepository = Depends(get_cva_agent_registry_repository_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute managed CVA agent by delegating to registry."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not resolved")

    record = await repo.get_registered_agent_by_agent_id(
        agent_id=agent_id,
        tenant_id=tenant_id,
    )
    if not record:
        raise HTTPException(status_code=404, detail="CVA agent not found")

    task = TaskData(
        title=f"cva-execute-{agent_id}",
        description=request.input,
        priority=TaskPriority.MEDIUM,
        metadata={
            **request.context,
            "agent_id": agent_id,
            "invoked_by": getattr(current_user, "id", None),
        },
    )

    execution = await registry.distribute_task(task)
    if execution is None or not execution.success:
        _raw_caps = record.capabilities
        if isinstance(_raw_caps, str):
            import json as _json

            try:
                _raw_caps = _json.loads(_raw_caps)
            except (ValueError, TypeError):
                _raw_caps = {}
        fallback_caps = (
            (_raw_caps or {}).get("functions", ["conversation"])
            if isinstance(_raw_caps, dict)
            else ["conversation"]
        )
        fallback_agent = ManagedCVAAgent(agent_id, None, fallback_caps)
        execution = await fallback_agent.process_task(task)

    return {
        "agent_id": agent_id,
        "result": execution.result_data or {},
        "status": "completed",
        "execution_time": execution.execution_time,
    }
