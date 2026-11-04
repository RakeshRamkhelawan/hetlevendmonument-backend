"""Memory Management System for M-MDP Implementation."""

from typing import Any

from .facade import MemoryManager
from .factory import (
    TenantContextError,
    get_memory_manager,
    get_memory_manager_for_tenant,
    resolve_memory_manager,
)
from .services import (
    CleanupService,
    EmbeddingService,
    EncryptionService,
    FAISSService,
    RedisService,
)
from .types import EpisodicMemory, MemoryEntry, StrategicMemory, TacticalMemory

__all__ = [
    # Types
    "MemoryEntry",
    "StrategicMemory",
    "TacticalMemory",
    "EpisodicMemory",
    # Main Class
    "MemoryManager",
    # Factory Functions
    "get_memory_manager_for_tenant",
    "get_memory_manager",
    "resolve_memory_manager",
    "TenantContextError",
    # Services
    "RedisService",
    "FAISSService",
    "EmbeddingService",
    "EncryptionService",
    "CleanupService",
]
