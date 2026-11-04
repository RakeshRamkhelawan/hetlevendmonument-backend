import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.memory.memory_manager import StrategicMemory, resolve_memory_manager
from src.core.shared.interfaces import AgentType

logger = logging.getLogger(__name__)


class MemoryHandler:
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.memory_initialized = False

    async def initialize(self) -> None:
        """Initialize M-MDP memory infrastructure"""
        if not self.memory_initialized:
            try:
                await resolve_memory_manager().initialize()
                self.memory_initialized = True
                logger.info("CVA strategic memory system initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize memory system: {e}")
                self.memory_initialized = False

    async def store_strategic_memory(
        self,
        strategy_type: str,
        content: str,
        success_rate: float,
        orchestration_pattern: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> str:
        """Store strategic memory for future retrieval"""
        try:
            memory = StrategicMemory(
                id=f"strategy_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{strategy_type}",
                timestamp=datetime.now(timezone.utc),
                agent_type=AgentType.CVA,
                content=content,
                strategy_type=strategy_type,
                success_rate=success_rate,
                orchestration_pattern=orchestration_pattern,
            )

            memory_id = await resolve_memory_manager().store_strategic_memory(memory)
            logger.info(f"Stored strategic memory: {memory_id}")
            return memory_id

        except Exception as e:
            logger.error(f"Failed to store strategic memory: {e}")
            return ""

    async def retrieve_strategic_memories(
        self, query: str, limit: int = 5
    ) -> list[StrategicMemory]:
        """Retrieve similar strategic memories for context"""
        try:
            memories = await resolve_memory_manager().retrieve_strategic_memories(query, limit)
            logger.info(f"Retrieved {len(memories)} strategic memories for query: {query}")
            return memories
        except Exception as e:
            logger.error(f"Failed to retrieve strategic memories: {e}")
            return []
