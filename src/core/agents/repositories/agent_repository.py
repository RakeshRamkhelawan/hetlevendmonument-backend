"""Concrete AgentRepository implementation.

Implements IAgentRepository (src.core.shared.interfaces) for the Agent ORM model.
Session is injected by the caller; this class never owns the transaction.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.models import Agent


class AgentRepository:
    """Tenant-isolated repository for Agent ORM objects.

    All read methods include a mandatory tenant_id filter so tenant A can never
    access tenant B data (ADR-005: tenant_id NOT NULL + repository isolation).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_agent_by_id(self, agent_id: int, tenant_id: int) -> Agent | None:
        """Return Agent by surrogate PK, filtered by tenant_id."""
        result = await self._session.execute(
            select(Agent).where(Agent.id == agent_id, Agent.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_agents_by_tenant(
        self, tenant_id: int, limit: int = 50, offset: int = 0
    ) -> list[Agent]:
        """Return paginated list of Agents for a tenant."""
        result = await self._session.execute(
            select(Agent).where(Agent.tenant_id == tenant_id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def save_agent(self, agent: Agent) -> Agent:
        """Persist (add + flush) an Agent. Caller owns the transaction."""
        self._session.add(agent)
        await self._session.flush()
        return agent
