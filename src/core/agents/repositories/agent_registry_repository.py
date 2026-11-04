"""Concrete AgentRegistryRepository implementation.

Implements IAgentRegistryRepository (src.core.shared.interfaces) for the
RegisteredAgent ORM model.
Session is injected by the caller; this class never owns the transaction.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import RegisteredAgent


class AgentRegistryRepository:
    """Tenant-isolated repository for RegisteredAgent ORM objects.

    All read methods include a mandatory tenant_id filter so tenant A can
    never access tenant B data (ADR-005: tenant_id NOT NULL + repository
    isolation).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_registered_agent_by_agent_id(
        self, agent_id: str, tenant_id: int
    ) -> RegisteredAgent | None:
        """Return RegisteredAgent by business-key, filtered by tenant_id."""
        result = await self._session.execute(
            select(RegisteredAgent).where(
                RegisteredAgent.agent_id == agent_id,
                RegisteredAgent.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_registered_agents(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[RegisteredAgent]:
        """Return paginated list of all RegisteredAgents for a tenant."""
        result = await self._session.execute(
            select(RegisteredAgent)
            .where(RegisteredAgent.tenant_id == tenant_id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_active_agents(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[RegisteredAgent]:
        """Return agents with a heartbeat within the last 5 minutes for a tenant.

        NOTE: last_heartbeat is nullable -- isnot(None) excludes agents that have
        never sent a heartbeat. The threshold comparison alone is insufficient on
        SQLite (test env) where NULL comparisons behave differently than PostgreSQL.
        """
        threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = await self._session.execute(
            select(RegisteredAgent)
            .where(
                RegisteredAgent.tenant_id == tenant_id,
                RegisteredAgent.last_heartbeat.isnot(None),
                RegisteredAgent.last_heartbeat >= threshold,
            )
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def register_agent(self, registration: RegisteredAgent) -> RegisteredAgent:
        """Persist a new RegisteredAgent. Caller owns the transaction."""
        self._session.add(registration)
        await self._session.flush()
        return registration

    # Columns that callers must never overwrite via update_agent.
    _IMMUTABLE_COLUMNS: frozenset[str] = frozenset({"id", "agent_id", "tenant_id"})

    async def update_agent(
        # TODO(TYPE): replace Any with concrete type
        self,
        agent_id: str,
        tenant_id: int,
        values: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Update an existing RegisteredAgent record. Caller owns the transaction."""
        safe_values = {k: v for k, v in values.items() if k not in self._IMMUTABLE_COLUMNS}
        await self._session.execute(
            update(RegisteredAgent)
            .where(
                RegisteredAgent.agent_id == agent_id,
                RegisteredAgent.tenant_id == tenant_id,
            )
            .values(**safe_values)
        )
        await self._session.flush()

    async def delete_agent(self, agent_id: str, tenant_id: int) -> None:
        """Delete a RegisteredAgent record. Caller owns the transaction."""
        await self._session.execute(
            delete(RegisteredAgent).where(
                RegisteredAgent.agent_id == agent_id,
                RegisteredAgent.tenant_id == tenant_id,
            )
        )
        await self._session.flush()
