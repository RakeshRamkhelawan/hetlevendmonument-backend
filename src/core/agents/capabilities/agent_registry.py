"""
Slice 8: AgentRegistry - Central Agent Registration and Discovery Service

Provides registry for agents with capability-based discovery and tenant isolation.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from src.core.agents.capabilities.schemas import AgentMetadata, AgentRegistration, AgentStatus


class AgentRegistry:
    """Central registry for agent registration and discovery"""

    def __init__(self) -> None:
        """Initialize in-memory agent registry"""
        self._agents: dict[UUID, AgentMetadata] = {}
        self._capability_index: dict[str, list[UUID]] = {}

    async def register_agent(
        self,
        registration: AgentRegistration,
    ) -> AgentMetadata:
        """
        Register a new agent with the registry

        Args:
            registration: Agent registration details

        Returns:
            AgentMetadata with generated agent_id
        """
        # Validate required fields
        if not registration.agent_type:
            raise ValueError("agent_type is required")
        if not registration.version:
            raise ValueError("version is required")
        if registration.tenant_id is None:
            raise ValueError("tenant_id is required")

        # Generate unique agent ID
        agent_id = uuid4()

        # Create metadata
        now = datetime.now(timezone.utc)
        metadata = AgentMetadata(
            agent_id=agent_id,
            agent_type=registration.agent_type,
            agent_name=registration.agent_name,
            version=registration.version,
            capabilities=registration.capabilities,
            tenant_id=registration.tenant_id,
            status=AgentStatus.ACTIVE,
            description=registration.description,
            metadata=registration.metadata,
            registered_at=now,
            updated_at=now,
        )

        # Store in registry
        self._agents[agent_id] = metadata

        # Index by capabilities
        for capability in registration.capabilities:
            if capability not in self._capability_index:
                self._capability_index[capability] = []
            self._capability_index[capability].append(agent_id)

        return metadata

    async def get_agent(
        self,
        agent_id: UUID,
        tenant_id: UUID,
    ) -> AgentMetadata | None:
        """
        Retrieve agent by ID with tenant isolation

        Args:
            agent_id: Agent identifier
            tenant_id: Current tenant ID

        Returns:
            AgentMetadata if found and accessible, None otherwise
        """
        agent = self._agents.get(agent_id)

        # Check tenant isolation
        if agent and agent.tenant_id != tenant_id:
            return None

        return agent

    async def find_agents_by_type(
        self,
        agent_type: str,
        tenant_id: UUID,
    ) -> list[AgentMetadata]:
        """
        Find all agents of a given type for tenant

        Args:
            agent_type: Type of agent to find
            tenant_id: Current tenant ID

        Returns: list[Any] of matching agents  # TODO(TYPE): replace Any with concrete type
        """
        return [
            agent
            for agent in self._agents.values()
            if agent.agent_type == agent_type and agent.tenant_id == tenant_id
        ]

    async def find_agents_by_capability(
        self,
        capability: str,
        tenant_id: UUID,
    ) -> list[AgentMetadata]:
        """
        Find all agents with a specific capability for tenant

        Args:
            capability: Capability to search for
            tenant_id: Current tenant ID

        Returns: list[Any] of matching agents  # TODO(TYPE): replace Any with concrete type
        """
        agent_ids = self._capability_index.get(capability, [])

        return [
            self._agents[agent_id]
            for agent_id in agent_ids
            if agent_id in self._agents and self._agents[agent_id].tenant_id == tenant_id
        ]

    async def list_agents(
        self,
        tenant_id: UUID,
        status_filter: AgentStatus | None = None,
    ) -> list[AgentMetadata]:
        """
        List all agents for tenant

        Args:
            tenant_id: Current tenant ID
            status_filter: Optional status filter

        Returns: list[Any] of all agents for tenant  # TODO(TYPE): replace Any with concrete type
        """
        agents = [agent for agent in self._agents.values() if agent.tenant_id == tenant_id]

        # Apply status filter if provided
        if status_filter is not None:
            agents = [agent for agent in agents if agent.status == status_filter]

        return agents

    async def update_agent_status(
        self,
        agent_id: UUID,
        status: AgentStatus,
        tenant_id: UUID,
    ) -> AgentMetadata:
        """
        Update agent status

        Args:
            agent_id: Agent to update
            status: New status
            tenant_id: Current tenant ID

        Returns:
            Updated AgentMetadata

        Raises:
            ValueError: If agent not found or access denied
        """
        agent = await self.get_agent(agent_id, tenant_id)

        if agent is None:
            raise ValueError(f"Agent {agent_id} not found or access denied")

        # Update status
        agent.status = status
        agent.updated_at = datetime.now(timezone.utc)

        # Update in storage
        self._agents[agent_id] = agent

        return agent

    async def unregister_agent(
        self,
        agent_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """
        Unregister an agent

        Args:
            agent_id: Agent to unregister
            tenant_id: Current tenant ID

        Returns:
            True if unregistered, False if not found or access denied
        """
        agent = await self.get_agent(agent_id, tenant_id)

        if agent is None:
            return False

        # Remove from capability index
        for capability in agent.capabilities:
            if capability in self._capability_index:
                self._capability_index[capability] = [
                    aid for aid in self._capability_index[capability] if aid != agent_id
                ]

        # Remove from registry
        del self._agents[agent_id]

        return True
