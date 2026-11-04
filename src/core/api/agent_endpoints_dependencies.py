"""Agent domain dependency facade for agent_endpoints.py (ADR-033 flat-file patroon)."""

from src.core.agents.agent_registry import AgentRegistry as AgentRegistry
from src.core.agents.models import RegisteredAgent as RegisteredAgent
from src.core.agents.repositories.agent_registry_repository import (
    AgentRegistryRepository as AgentRegistryRepository,
)

__all__ = ["AgentRegistry", "AgentRegistryRepository", "RegisteredAgent"]
