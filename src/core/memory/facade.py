"""Memory Manager Facade - maintains backward compatible API."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from collections.abc import Iterable

from src.core.memory.services import (
    CleanupService,
    EmbeddingService,
    EncryptionService,
    FAISSService,
    RedisService,
)
from src.core.memory.types import EpisodicMemory, MemoryEntry, StrategicMemory, TacticalMemory
from src.core.types import AgentType

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Centralized memory management for M-MDP system with encryption support.

    This is a facade class that delegates to specialized services:
    - RedisService: Redis persistence operations
    - FAISSService: Vector index operations
    - EmbeddingService: Generate embeddings
    - EncryptionService: Encrypt/decrypt embeddings
    - CleanupService: Memory cleanup operations

    P2 FIX: Supports embedding encryption to prevent data exposure in FAISS indices.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        tenant_id: int | None = None,
        encryption_key: bytes | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self._encryption_enabled = encryption_key is not None

        # Initialize services
        self._redis_service = RedisService(redis_url, tenant_id)
        self._faiss_service = FAISSService(dimension=384)
        self._embedding_service = EmbeddingService()
        self._encryption_service = EncryptionService(encryption_key)
        self._cleanup_service = CleanupService()

        # Memory storage
        self.strategic_memories: list[StrategicMemory] = []
        self.tactical_memories: list[TacticalMemory] = []
        self.episodic_memories: list[EpisodicMemory] = []

        # Configuration
        self.max_memories = {"strategic": 1000, "tactical": 5000, "episodic": 10000}

    # Legacy properties for backward compatibility
    @property
    def redis_client(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Access to Redis client (legacy compatibility)."""
        return self._redis_service._client

    @redis_client.setter
    def redis_client(self, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set Redis client (legacy compatibility for tests)."""
        self._redis_service._client = value

    @property
    def embedding_model(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Access to embedding model (legacy compatibility)."""
        return self._embedding_service._model

    @embedding_model.setter
    def embedding_model(self, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set embedding model (legacy compatibility)."""
        self._embedding_service._model = value

    @property
    def strategic_index(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Access to strategic FAISS index (legacy compatibility)."""
        return self._faiss_service.get_index("strategic")

    @strategic_index.setter
    def strategic_index(self, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set strategic FAISS index (legacy compatibility for tests)."""
        self._faiss_service._indices["strategic"] = value

    @property
    def tactical_index(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Access to tactical FAISS index (legacy compatibility)."""
        return self._faiss_service.get_index("tactical")

    @tactical_index.setter
    def tactical_index(self, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set tactical FAISS index (legacy compatibility for tests)."""
        self._faiss_service._indices["tactical"] = value

    @property
    def episodic_index(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Access to episodic FAISS index (legacy compatibility)."""
        return self._faiss_service.get_index("episodic")

    @episodic_index.setter
    def episodic_index(self, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set episodic FAISS index (legacy compatibility for tests)."""
        self._faiss_service._indices["episodic"] = value

    def _redis_key(self, memory_type: str) -> str:
        """Return a tenant-scoped Redis key (legacy compatibility)."""
        return self._redis_service._make_key(memory_type)

    async def initialize(self) -> None:
        """Initialize memory manager components"""
        # Connect to Redis
        await self._redis_service.initialize()

        # Initialize embedding model (lazy-load on first use)
        await self._embedding_service.initialize()

        # Initialize FAISS indices
        self._faiss_service.create_index("strategic")
        self._faiss_service.create_index("tactical")
        self._faiss_service.create_index("episodic")

        # Load existing memories
        await self._load_memories()

    async def _ensure_initialized(self) -> None:
        """Ensure all memory components are initialized (Lazy-loading)"""
        await self._redis_service.initialize()
        await self._embedding_service.initialize()

        # Ensure FAISS indices exist
        if not self._faiss_service.has_index("strategic"):
            self._faiss_service.create_index("strategic")
            self._faiss_service.create_index("tactical")
            self._faiss_service.create_index("episodic")

    async def _load_memories(self) -> None:
        """Load memories from Redis persistence with decryption."""
        try:
            # Load strategic memories
            strategic_data = await self._redis_service.get("strategic")
            if strategic_data:
                strategic_list = cast(list[dict[str, Any]], json.loads(strategic_data))  # TODO(TYPE): replace Any with concrete type
                self.strategic_memories = cast(
                    list[StrategicMemory],
                    [StrategicMemory.from_dict(data) for data in strategic_list],
                )
                # Decrypt embeddings
                for mem in self.strategic_memories:
                    mem.decrypt_embedding(self._encryption_service)
                # Rebuild index
                await self._rebuild_strategic_index()

            # Load tactical memories
            tactical_data = await self._redis_service.get("tactical")
            if tactical_data:
                tactical_list = cast(list[dict[str, Any]], json.loads(tactical_data))  # TODO(TYPE): replace Any with concrete type
                self.tactical_memories = cast(
                    list[TacticalMemory], [TacticalMemory.from_dict(data) for data in tactical_list]
                )
                for tactical_mem in self.tactical_memories:
                    tactical_mem.decrypt_embedding(self._encryption_service)
                await self._rebuild_tactical_index()

            # Load episodic memories
            episodic_data = await self._redis_service.get("episodic")
            if episodic_data:
                episodic_list = cast(list[dict[str, Any]], json.loads(episodic_data))  # TODO(TYPE): replace Any with concrete type
                self.episodic_memories = cast(
                    list[EpisodicMemory], [EpisodicMemory.from_dict(data) for data in episodic_list]
                )
                for episodic_mem in self.episodic_memories:
                    episodic_mem.decrypt_embedding(self._encryption_service)
                await self._rebuild_episodic_index()

        except Exception as e:
            logger.error("Error loading memories: %s", e)

    async def _rebuild_strategic_index(self) -> None:
        """Rebuild strategic FAISS index."""
        embeddings = [mem.embedding for mem in self.strategic_memories if mem.embedding is not None]
        self._faiss_service.rebuild_from_vectors("strategic", embeddings)

    async def _rebuild_tactical_index(self) -> None:
        """Rebuild tactical FAISS index."""
        embeddings = [mem.embedding for mem in self.tactical_memories if mem.embedding is not None]
        self._faiss_service.rebuild_from_vectors("tactical", embeddings)

    async def _rebuild_episodic_index(self) -> None:
        """Rebuild episodic FAISS index."""
        embeddings = [mem.embedding for mem in self.episodic_memories if mem.embedding is not None]
        self._faiss_service.rebuild_from_vectors("episodic", embeddings)

    async def _rebuild_indices(self) -> None:
        """Rebuild all FAISS indices with legacy no-raise behavior."""
        try:
            if self.strategic_index is None:
                self._faiss_service.create_index("strategic")
            if self.tactical_index is None:
                self._faiss_service.create_index("tactical")
            if self.episodic_index is None:
                self._faiss_service.create_index("episodic")

            await self._rebuild_strategic_index()
            await self._rebuild_tactical_index()
            await self._rebuild_episodic_index()
        except Exception as exc:
            logger.error("Failed to rebuild memory indices: %s", exc)

    async def store_strategic_memory(self, memory: StrategicMemory) -> str:
        """Store strategic memory with vector embedding"""
        await self._ensure_initialized()

        # Generate embedding
        memory.embedding = self._embedding_service.encode(memory.content)

        # Add to collection
        self.strategic_memories.append(memory)

        # Add to FAISS index
        self._faiss_service.add_vectors("strategic", [memory.embedding])

        # Maintain size limit
        if len(self.strategic_memories) > self.max_memories["strategic"]:
            self.strategic_memories.pop(0)

        # Persist to Redis
        await self._persist_strategic_memories()

        return memory.id

    async def store_tactical_memory(self, memory: TacticalMemory) -> str:
        """Store tactical memory with vector embedding"""
        await self._ensure_initialized()

        memory.embedding = self._embedding_service.encode(memory.content)
        self.tactical_memories.append(memory)
        self._faiss_service.add_vectors("tactical", [memory.embedding])

        if len(self.tactical_memories) > self.max_memories["tactical"]:
            self.tactical_memories.pop(0)

        await self._persist_tactical_memories()
        return memory.id

    async def store_episodic_memory(self, memory: EpisodicMemory) -> str:
        """Store episodic memory with vector embedding"""
        await self._ensure_initialized()

        memory.embedding = self._embedding_service.encode(memory.content)
        self.episodic_memories.append(memory)
        self._faiss_service.add_vectors("episodic", [memory.embedding])

        if len(self.episodic_memories) > self.max_memories["episodic"]:
            self.episodic_memories.pop(0)

        await self._persist_episodic_memories()
        return memory.id

    async def retrieve_strategic_memories(
        self, query: str, limit: int = 5
    ) -> list[StrategicMemory]:
        """Retrieve similar strategic memories using vector search"""
        await self._ensure_initialized()
        if not self.strategic_memories:
            return []

        query_embedding = self._embedding_service.encode(query)
        scores, indices = self._faiss_service.search("strategic", query_embedding, limit)

        if scores is None or indices is None:
            return []

        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        index_values = cast(Iterable[int], indices)
        score_values = cast(Iterable[float], scores)
        for i, score in zip(index_values, score_values):
            if i < len(self.strategic_memories):
                memory = self.strategic_memories[i]
                memory.context_similarity = float(score)
                results.append(memory)

        return results

    async def retrieve_tactical_memories(self, query: str, limit: int = 10) -> list[TacticalMemory]:
        """Retrieve similar tactical memories"""
        await self._ensure_initialized()
        if not self.tactical_memories:
            return []

        query_embedding = self._embedding_service.encode(query)
        scores, indices = self._faiss_service.search("tactical", query_embedding, limit)

        if scores is None or indices is None:
            return []

        index_values = cast(Iterable[int], indices)
        return [self.tactical_memories[i] for i in index_values if i < len(self.tactical_memories)]

    async def retrieve_episodic_memories(self, query: str, limit: int = 20) -> list[EpisodicMemory]:
        """Retrieve similar episodic memories"""
        await self._ensure_initialized()
        if not self.episodic_memories:
            return []

        query_embedding = self._embedding_service.encode(query)
        scores, indices = self._faiss_service.search("episodic", query_embedding, limit)

        if scores is None or indices is None:
            return []

        index_values = cast(Iterable[int], indices)
        return [self.episodic_memories[i] for i in index_values if i < len(self.episodic_memories)]

    async def _persist_strategic_memories(self) -> None:
        """Persist strategic memories to Redis with encryption."""
        # Encrypt embeddings before serialization
        for mem in self.strategic_memories:
            mem.encrypt_embedding(self._encryption_service)

        data = [mem.to_dict() for mem in self.strategic_memories]
        await self._redis_service.set_json("strategic", data)

        # Decrypt after serialization for continued use
        for mem in self.strategic_memories:
            mem.decrypt_embedding(self._encryption_service)

    async def _persist_tactical_memories(self) -> None:
        """Persist tactical memories to Redis with encryption."""
        for mem in self.tactical_memories:
            mem.encrypt_embedding(self._encryption_service)

        data = [mem.to_dict() for mem in self.tactical_memories]
        await self._redis_service.set_json("tactical", data)

        for mem in self.tactical_memories:
            mem.decrypt_embedding(self._encryption_service)

    async def _persist_episodic_memories(self) -> None:
        """Persist episodic memories to Redis with encryption."""
        for mem in self.episodic_memories:
            mem.encrypt_embedding(self._encryption_service)

        data = [mem.to_dict() for mem in self.episodic_memories]
        await self._redis_service.set_json("episodic", data)

        for mem in self.episodic_memories:
            mem.decrypt_embedding(self._encryption_service)

    # RL Learning Integration
    async def store_memory(
        self,
        agent_id: str,
        memory_type: str,
        content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        importance_score: float = 0.5,
    ) -> str:
        """Generic memory storage for RL learning integration"""
        try:
            memory_id = f"{agent_id}_{memory_type}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            if memory_type in ["strategy", "strategic"]:
                if self.embedding_model is None or not hasattr(self.embedding_model, "encode"):
                    return ""

                memory = StrategicMemory(
                    id=memory_id,
                    timestamp=datetime.now(timezone.utc),
                    agent_type=AgentType.CVA,
                    content=json.dumps(content),
                    metadata={
                        "agent_id": agent_id,
                        "importance_score": importance_score,
                        "rl_learning": True,
                    },
                    strategy_type=content.get("strategy_type", "learned_pattern"),
                )
                return await self.store_strategic_memory(memory)

            elif memory_type in ["experience", "learning_episode", "learning_outcome"]:
                return ""

            else:
                return ""

        except Exception as e:
            logger.error("Failed to store RL memory: %s", e)
            return ""

    async def query_memories(
        self,
        agent_id: str,
        memory_types: list[str],
        query_vector: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        top_k: int = 5,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Query memories for RL learning integration"""
        await self._ensure_initialized()
        try:
            results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

            for memory_type in memory_types:
                memories: list[MemoryEntry]
                if memory_type in ["strategy", "strategic"]:
                    memories = cast(
                        list[MemoryEntry],
                        await self.retrieve_strategic_memories(
                            json.dumps({"agent_id": agent_id}), top_k
                        ),
                    )
                elif memory_type in [
                    "experience",
                    "learning_episode",
                    "learning_outcome",
                ]:
                    memories = cast(
                        list[MemoryEntry],
                        await self.retrieve_episodic_memories(
                            json.dumps({"agent_id": agent_id}), top_k
                        ),
                    )
                else:
                    memories = cast(
                        list[MemoryEntry],
                        await self.retrieve_tactical_memories(
                            json.dumps({"agent_id": agent_id}), top_k
                        ),
                    )

                for memory in memories:
                    if memory.metadata and memory.metadata.get("agent_id") == agent_id:
                        content_data: dict[str, Any] = (  # TODO(TYPE): replace Any with concrete type
                            cast(dict[str, Any], json.loads(memory.content))  # TODO(TYPE): replace Any with concrete type
                            if memory.content
                            else {}
                        )
                        rl_memory = {
                            "memory_id": memory.id,
                            "content": content_data,
                            "importance_score": memory.metadata.get("importance_score", 0.0),
                            "timestamp": memory.timestamp,
                            "memory_type": memory_type,
                        }
                        results.append(rl_memory)

            results.sort(key=lambda x: x["importance_score"], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error("Failed to query RL memories: %s", e)
            return []

    async def update_memory_importance(
        self,
        memory_id: str,
        new_importance: float,
    ) -> bool:
        """Update a memory importance score across all memory stores."""
        try:
            memory_groups: list[tuple[str, list[MemoryEntry]]] = [
                ("strategic", cast(list[MemoryEntry], self.strategic_memories)),
                ("tactical", cast(list[MemoryEntry], self.tactical_memories)),
                ("episodic", cast(list[MemoryEntry], self.episodic_memories)),
            ]

            for memory_type, memories in memory_groups:
                for memory in memories:
                    if memory.id != memory_id:
                        continue

                    if memory.metadata is None:
                        memory.metadata = {}
                    memory.metadata["importance_score"] = new_importance

                    if memory_type == "strategic":
                        await self._persist_strategic_memories()
                    elif memory_type == "tactical":
                        await self._persist_tactical_memories()
                    else:
                        await self._persist_episodic_memories()

                    return True

            return False
        except Exception as exc:
            logger.error("Failed to update memory importance: %s", exc)
            return False

    async def get_learning_context(self, agent_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return a compact RL-style learning context for an agent."""
        try:
            memories = await self.query_memories(
                agent_id=agent_id,
                memory_types=["strategy", "tactical", "experience"],
                top_k=20,
            )

            importance_scores = [float(memory.get("importance_score", 0.0)) for memory in memories]
            successful_patterns = [score for score in importance_scores if score >= 0.8]

            learning_trend = "stable"
            if len(importance_scores) >= 2:
                midpoint = max(1, len(importance_scores) // 2)
                earlier = importance_scores[:midpoint]
                later = importance_scores[midpoint:]
                earlier_avg = sum(earlier) / len(earlier)
                later_avg = sum(later) / len(later) if later else earlier_avg
                if later_avg > earlier_avg:
                    learning_trend = "improving"
                elif later_avg < earlier_avg:
                    learning_trend = "declining"

            recent_memory_types = list(
                dict.fromkeys(memory.get("memory_type", "unknown") for memory in memories)
            )

            return {
                "agent_id": agent_id,
                "total_memories": len(memories),
                "successful_patterns_count": len(successful_patterns),
                "learning_trend": learning_trend,
                "recent_memory_types": recent_memory_types,
                "last_update": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            logger.error("Failed to build learning context: %s", exc)
            return {}

    async def cleanup_old_memories(self, days_old: int = 30) -> dict[str, int]:
        """Cleanup old memories to maintain performance"""

        def get_timestamp(mem: MemoryEntry) -> datetime:
            return mem.timestamp

        def get_importance(mem: MemoryEntry) -> float:
            return mem.metadata.get("importance_score", 0.0) if mem.metadata else 0.0

        try:
            # Cleanup strategic memories
            original_count = len(self.strategic_memories)
            self.strategic_memories = self._cleanup_service.filter_by_age_and_importance(
                self.strategic_memories,
                datetime.now(timezone.utc) - timedelta(days=days_old),
                get_timestamp,
                get_importance,
            )
            strategic_removed = original_count - len(self.strategic_memories)

            # Cleanup tactical memories
            original_count = len(self.tactical_memories)
            self.tactical_memories = self._cleanup_service.filter_by_age_and_importance(
                self.tactical_memories,
                datetime.now(timezone.utc) - timedelta(days=days_old),
                get_timestamp,
                get_importance,
            )
            tactical_removed = original_count - len(self.tactical_memories)

            # Cleanup episodic memories
            original_count = len(self.episodic_memories)
            self.episodic_memories = self._cleanup_service.filter_by_age_and_importance(
                self.episodic_memories,
                datetime.now(timezone.utc) - timedelta(days=days_old),
                get_timestamp,
                get_importance,
            )
            episodic_removed = original_count - len(self.episodic_memories)

            # Rebuild indices after cleanup
            await self._rebuild_strategic_index()
            await self._rebuild_tactical_index()
            await self._rebuild_episodic_index()

            # Persist cleaned memories
            await self._persist_strategic_memories()
            await self._persist_tactical_memories()
            await self._persist_episodic_memories()

            return {
                "strategic": strategic_removed,
                "tactical": tactical_removed,
                "episodic": episodic_removed,
            }

        except Exception as e:
            logger.error("Failed to cleanup old memories: %s", e)
            return {"strategic": 0, "tactical": 0, "episodic": 0}

    async def get_memory_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get memory system statistics"""
        rl_memories = {
            "strategic": len(
                [m for m in self.strategic_memories if m.metadata and m.metadata.get("rl_learning")]
            ),
            "tactical": len(
                [m for m in self.tactical_memories if m.metadata and m.metadata.get("rl_learning")]
            ),
            "episodic": len(
                [m for m in self.episodic_memories if m.metadata and m.metadata.get("rl_learning")]
            ),
        }

        return {
            "strategic_count": len(self.strategic_memories),
            "tactical_count": len(self.tactical_memories),
            "episodic_count": len(self.episodic_memories),
            "strategic_limit": self.max_memories["strategic"],
            "tactical_limit": self.max_memories["tactical"],
            "episodic_limit": self.max_memories["episodic"],
            "embedding_model": self._embedding_service.get_model_name(),
            "vector_dimension": self._embedding_service.get_dimension(),
            "rl_learning_memories": rl_memories,
            "total_rl_memories": sum(rl_memories.values()),
            "encryption_enabled": self._encryption_service.is_enabled,
        }

    async def cleanup(self) -> None:
        """Cleanup resources"""
        client = self.redis_client
        if client is not None:
            await client.close()
