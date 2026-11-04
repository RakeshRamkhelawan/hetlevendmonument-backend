#!/usr/bin/env python3
"""
Memory Management System for M-MDP Implementation
Provides strategic, tactical, and episodic memory capabilities

NOTE: This module now re-exports from src.core.memory for backward compatibility.
The actual implementation has been refactored into a service-based architecture.
"""

# Re-export all public APIs from the new memory package

from src.core.memory.facade import MemoryManager
from src.core.memory.factory import (
    TenantContextError,
    get_memory_manager,
    get_memory_manager_for_tenant,
    resolve_memory_manager,
)
from src.core.memory.services import (
    CleanupService,
    EmbeddingService,
    EncryptionService,
    FAISSService,
    RedisService,
)
from src.core.memory.services.embedding_service import _get_embedding_model
from src.core.memory.services.faiss_service import _get_faiss
from src.core.memory.types import (
    EpisodicMemory,
    MemoryEntry,
    StrategicMemory,
    TacticalMemory,
    _get_numpy,
)

# Legacy module-level singleton for backward compatibility with older imports.
memory_manager = get_memory_manager()


def _get_sentence_transformer() -> object:
    """Backward-compatible alias for the embedding model lazy loader."""
    return _get_embedding_model()


__all__ = [
    # Types
    "MemoryEntry",
    "StrategicMemory",
    "TacticalMemory",
    "EpisodicMemory",
    "_get_numpy",
    "_get_faiss",
    "_get_sentence_transformer",
    # Main Class
    "MemoryManager",
    # Factory Functions
    "get_memory_manager_for_tenant",
    "get_memory_manager",
    "resolve_memory_manager",
    "memory_manager",
    "TenantContextError",
    # Services
    "RedisService",
    "FAISSService",
    "EmbeddingService",
    "EncryptionService",
    "CleanupService",
]
