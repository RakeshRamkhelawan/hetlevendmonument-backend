from typing import Any

"""
Memory Domain - Digital Twin Persistent Memory Layer
=====================================================

Sprint A: Core schema + write path + retrieval + boot context.

This domain provides tenant-scoped, agent-scoped persistent memory:
- AgentMemoryProfile: identity, goals, operating rules per agent per tenant
- MemoryItem: durable facts, episodes, preferences, summaries
- SessionMemoryEvent: append-only event log per session
- MemoryConsolidationRun: nightly batch job tracking

Usage:
    from src.domains.memory.models import AgentMemoryProfile, MemoryItem
    from src.domains.memory.services.memory_write_service import MemoryWriteService
    from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService
    from src.domains.memory.services.context_packer_service import ContextPackerService
"""
