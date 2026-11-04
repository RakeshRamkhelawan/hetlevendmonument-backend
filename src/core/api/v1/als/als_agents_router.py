"""ALS agents sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.als.dependencies import OrganismRegistry, Signal, SignalTier, get_db
from src.core.api.v1.als.shared import ALS_ORCHESTRATOR_TIMEOUT_SECONDS, get_orchestrator
from src.core.middleware.tenant_context import get_current_tenant_id

logger = logging.getLogger(__name__)

als_agents_router = APIRouter()


@als_agents_router.get("/agents")
async def list_agents(
    tenant_id: int = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """List all registered agents in the organism."""
    result = await db.execute(
        select(OrganismRegistry).where(OrganismRegistry.tenant_id == tenant_id)
    )
    agents = result.scalars().all()

    return [
        {
            "agent_id": agent.agent_id,
            "agent_type": agent.agent_type,
            "department": agent.department,
            "status": agent.status,
            "last_heartbeat": (agent.last_heartbeat.isoformat() if agent.last_heartbeat else None),
        }
        for agent in agents
    ]


@als_agents_router.post("/agents/{agent_id}/ping")
async def ping_agent(
    agent_id: str,
    tenant_id: int = Depends(get_current_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Ping a specific agent to check if it's responsive."""
    signal = Signal(
        tenant_id=tenant_id,
        source_agent_id="als_api",
        target_agent_ids=[agent_id],
        tier=SignalTier.COGNITIVE,
        payload={
            "action": "ping",
            "agent_id": agent_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    try:
        await asyncio.wait_for(
            get_orchestrator(tenant_id).signal_bus.emit(signal),
            timeout=ALS_ORCHESTRATOR_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="ALS ping timed out")
    except Exception as exc:
        logger.error(
            "als_ping_failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id, "agent_id": agent_id},
        )
        raise HTTPException(status_code=503, detail="Signal bus unavailable")

    logger.info("als_ping_sent: agent_id=%s, tenant_id=%s", agent_id, tenant_id)
    return {"success": True, "data": {"agent_id": agent_id, "ping": "sent"}}


@als_agents_router.get("/agents/{agent_id}/heartbeat")
async def get_agent_heartbeat(
    agent_id: str,
    tenant_id: int = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get heartbeat status for a specific registered agent."""
    result = await db.execute(
        select(OrganismRegistry).where(
            OrganismRegistry.agent_id == agent_id,
            OrganismRegistry.tenant_id == tenant_id,
        )
    )
    agent = result.scalar_one_or_none()

    if agent is None:
        return {
            "success": True,
            "data": {
                "agent_id": agent_id,
                "status": "unknown",
                "last_seen": None,
                "response_time_ms": None,
                "error_rate": None,
            },
        }

    return {
        "success": True,
        "data": {
            "agent_id": agent_id,
            "status": agent.status or "unknown",
            "last_seen": (agent.last_heartbeat.isoformat() if agent.last_heartbeat else None),
            "response_time_ms": None,
            "error_rate": None,
        },
    }
