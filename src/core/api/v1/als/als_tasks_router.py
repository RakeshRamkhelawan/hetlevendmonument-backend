"""ALS tasks/broadcast sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.als.shared import (
    ALS_ORCHESTRATOR_TIMEOUT_SECONDS,
    TaskRequest,
    TaskResponse,
    get_orchestrator,
)
from src.core.auth.api_deps import UserResponse, get_current_user_dependency
from src.core.api.v1.als.council_dependencies import build_council, require_council_approval
from src.core.api.v1.als.dependencies import get_db
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.types import TaskPriority

logger = logging.getLogger(__name__)

als_tasks_router = APIRouter()


@als_tasks_router.post("/tasks", response_model=TaskResponse)
async def delegate_task(
    request: TaskRequest,
    tenant_id: int = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> TaskResponse:
    """Delegate a task to the symbiotic organism. Governed by AgentCouncil (ADR-031)."""
    from src.core.shared.interfaces import TaskData

    council = await build_council(db)
    await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=current_user.id,
        action_type="als.delegate_task",
        action_params={
            "task_type": request.task_type,
            "preferred_agents": request.preferred_agents or [],
        },
        reasoning=f"ALS task delegation: {request.task_type}",
        confidence=1.0,
        db=db,
    )

    orchestrator = get_orchestrator(tenant_id)

    task = TaskData(
        id=f"task_{tenant_id}_{id(request)}",
        title=request.task_type,
        description=str(request.payload),
        priority=TaskPriority.HIGH,
        metadata=request.payload,
    )

    try:
        result = await asyncio.wait_for(
            orchestrator.delegate_task(task=task, preferred_agents=request.preferred_agents),
            timeout=ALS_ORCHESTRATOR_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="ALS task delegation timed out")

    return TaskResponse(
        success=result.success,
        task_id=result.task_id,
        assigned_agent=result.data.get("assigned_agent") if result.data else None,
        error=result.error,
    )


@als_tasks_router.post("/broadcast")
async def broadcast_message(
    message_type: str,
    payload: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    tenant_id: int = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Broadcast a message to all agents. Governed by AgentCouncil (ADR-031)."""
    council = await build_council(db)
    await require_council_approval(
        council=council,
        tenant_id=tenant_id,
        user_id=current_user.id,
        action_type="als.broadcast",
        action_params={"message_type": message_type, "payload_keys": list(payload.keys())},
        reasoning=f"ALS broadcast: {message_type}",
        confidence=1.0,
        db=db,
    )

    orchestrator = get_orchestrator(tenant_id)

    try:
        signal_ids = await asyncio.wait_for(
            orchestrator.broadcast_to_all(message_type=message_type, payload=payload),
            timeout=ALS_ORCHESTRATOR_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="ALS broadcast timed out")

    return {"broadcast": True, "signal_ids": signal_ids, "tenant_id": tenant_id}
