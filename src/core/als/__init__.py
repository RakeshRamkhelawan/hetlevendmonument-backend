"""
Agent Learning System (ALS)

Professional implementation with all critical fixes applied.
"""

__version__ = "3.1.0"

# Models
from typing import Any

# Infrastructure
from src.core.als.infrastructure.redis_pool import RedisPoolManager
from src.core.als.models.schemas import (
    AgentRegister,
    AgentStatus,
    APIResponse,
    InsightCreate,
    SignalCreate,
    SignalStatus,
    SignalTier,
    SwarmCreate,
    ThreatLevel,
)

__all__ = [
    "RedisPoolManager",
    "SignalTier",
    "SignalStatus",
    "AgentStatus",
    "ThreatLevel",
    "SignalCreate",
    "AgentRegister",
    "InsightCreate",
    "SwarmCreate",
    "APIResponse",
]
