"""
Agent Domain Services - FASE 1.2 DDD
Business logic that doesn't belong to a single entity
"""

from typing import Any, Optional

from .models import Agent, AgentStatus, AgentType
from .repositories import AgentRepository


class AgentService:
    """
    Agent Domain Service
    Orchestrates agent operations and business logic
    """

    def __init__(self, repository: AgentRepository) -> None:
        self.repository = repository

    async def create_agent(
        self,
        name: str,
        agent_type: AgentType,
        tenant_id: str,
        capabilities: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Agent:
        """
        Create new agent with business rules validation
        """
        # Business rule: Agent name must be unique within tenant
        existing = await self.repository.find_by_name_and_tenant(name, tenant_id)
        if existing:
            raise ValueError(f"Agent with name '{name}' already exists for this tenant")

        agent = Agent(
            id=self._generate_agent_id(),
            name=name,
            agent_type=agent_type,
            tenant_id=tenant_id,
            capabilities=capabilities or {},
            status=AgentStatus.INACTIVE,
        )

        # Publish domain event
        agent.add_domain_event(
            {
                "type": "agent.created",
                "aggregate_id": agent.id,
                "data": {
                    "agent_id": agent.id,
                    "name": name,
                    "type": agent_type.value,
                    "tenant_id": tenant_id,
                },
            }
        )

        await self.repository.save(agent)
        return agent

    async def activate_agent(self, agent_id: str) -> Agent:
        """Activate agent with validation"""
        agent = await self.repository.find_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent.activate()
        await self.repository.save(agent)
        return agent

    async def get_tenant_agents(
        self,
        tenant_id: str,
        agent_type: AgentType | None = None,
        status: AgentStatus | None = None,
    ) -> list[Agent]:
        """Get all agents for a tenant with optional filtering"""
        return await self.repository.find_by_tenant(tenant_id, agent_type=agent_type, status=status)

    def _generate_agent_id(self) -> str:
        """Generate unique agent ID"""
        import uuid

        return f"agent_{uuid.uuid4().hex[:12]}"
