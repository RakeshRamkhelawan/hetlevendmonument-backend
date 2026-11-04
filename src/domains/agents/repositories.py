"""
Agent Repository Interface - FASE 1.2 DDD
Defines contract for agent persistence
"""

from abc import ABC, abstractmethod
from typing import Optional

from .models import Agent, AgentStatus, AgentType


class AgentRepository(ABC):
    """
    Repository interface for Agent aggregate
    Infrastructure layer will provide concrete implementation
    """

    @abstractmethod
    async def save(self, agent: Agent) -> Agent:
        """Save or update agent"""
        pass

    @abstractmethod
    async def find_by_id(self, agent_id: str) -> Agent | None:
        """Find agent by ID"""
        pass

    @abstractmethod
    async def find_by_name_and_tenant(self, name: str, tenant_id: str) -> Agent | None:
        """Find agent by name within tenant"""
        pass

    @abstractmethod
    async def find_by_tenant(
        self,
        tenant_id: str,
        agent_type: AgentType | None = None,
        status: AgentStatus | None = None,
    ) -> list[Agent]:
        """Find all agents for tenant with optional filters"""
        pass

    @abstractmethod
    async def delete(self, agent_id: str) -> bool:
        """Delete agent"""
        pass
