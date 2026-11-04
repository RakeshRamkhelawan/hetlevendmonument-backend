"""Dependency facade for assistant_endpoints.py (ADR-033 flat-file patroon)."""

from src.core.agents.ultimate_cva.agent import UltimateCVAAgent as UltimateCVAAgent
from src.core.agents.ultimate_cva.agent import (
    create_ultimate_cva_agent as create_ultimate_cva_agent,
)
from src.core.agents.ultimate_cva.memory import ConversationMemory as ConversationMemory
from src.core.agents.ultimate_cva.models import UltimateExecutionResult as UltimateExecutionResult
from src.core.database.redis import get_redis_client as get_redis_client

__all__ = [
    "ConversationMemory",
    "UltimateExecutionResult",
    "UltimateCVAAgent",
    "create_ultimate_cva_agent",
    "get_redis_client",
]
