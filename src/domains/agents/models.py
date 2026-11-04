"""
Agent Domain Models - FASE 1.2 DDD
"""

from typing import Any, Optional

from pydantic import Field

# Import types from single source of truth
from src.core.types import AgentStatus, AgentType
from src.domains.shared import AggregateRoot

__all__ = [
    "AgentStatus",
    "AgentType",
    "Agent",
]


class Agent(AggregateRoot):
    """
    Agent Aggregate Root
    Represents an AI agent in the system
    """

    name: str = Field(..., min_length=1, max_length=200)
    agent_type: AgentType
    status: AgentStatus = AgentStatus.INACTIVE
    tenant_id: str
    capabilities: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    configuration: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def activate(self) -> None:
        """Activate the agent"""
        if self.status == AgentStatus.ARCHIVED:
            raise ValueError("Cannot activate archived agent")

        self.status = AgentStatus.ACTIVE
        self.add_domain_event(
            {
                "type": "agent.activated",
                "aggregate_id": self.id,
                "data": {"agent_id": self.id, "name": self.name},
            }
        )

    def deactivate(self) -> None:
        """Deactivate the agent"""
        self.status = AgentStatus.INACTIVE
        self.add_domain_event(
            {
                "type": "agent.deactivated",
                "aggregate_id": self.id,
                "data": {"agent_id": self.id},
            }
        )

    def archive(self) -> None:
        """Archive the agent (soft delete)"""
        self.status = AgentStatus.ARCHIVED
        self.add_domain_event(
            {
                "type": "agent.archived",
                "aggregate_id": self.id,
                "data": {"agent_id": self.id},
            }
        )

    def update_configuration(self, config: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Update agent configuration"""
        self.configuration.update(config)
        self.add_domain_event(
            {
                "type": "agent.configuration_updated",
                "aggregate_id": self.id,
                "data": {"agent_id": self.id, "config": config},
            }
        )
