"""
Knowledge Manager - Central orchestrator for all knowledge operations
Manages knowledge bases, retrieval, and indexing
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.caching import cache_system
from src.core.caching.cache_layer import cached
from src.core.shared.production_logging import SafeLogger

from .embedding_service import EmbeddingService
from .knowledge_base import KnowledgeBase, KnowledgeEntry, KnowledgeType
from .knowledge_graph import KnowledgeGraph
from .retrieval_engine import RetrievalEngine, SearchQuery, SearchResult

logger = SafeLogger(__name__)


class OperationStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"


@dataclass
class KnowledgeStats:
    """Knowledge system statistics"""

    total_entries: int = 0
    entries_by_type: dict[str, int] = field(default_factory=dict)
    indexed_entries: int = 0
    last_update: datetime | None = None
    cache_hit_rate: float = 0.0
    avg_retrieval_time: float = 0.0


class KnowledgeManager:
    """
    Central knowledge management system
    Coordinates knowledge storage, retrieval, and maintenance
    """

    def __init__(self) -> None:
        self.knowledge_bases: dict[str, KnowledgeBase] = {}
        self.retrieval_engine: RetrievalEngine | None = None
        self.embedding_service: EmbeddingService | None = None
        self.knowledge_graph: KnowledgeGraph | None = None
        self._initialized = False
        self._stats = KnowledgeStats()
        self._operation_history: list[
            dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        ] = []  # TODO(TYPE): replace Any with concrete type

    async def initialize(self) -> bool:
        """Initialize all knowledge system components"""
        if self._initialized:
            return True

        try:
            logger.info("Initializing Knowledge Management System")

            # Initialize embedding service
            self.embedding_service = EmbeddingService()
            await self.embedding_service.initialize()

            # Initialize retrieval engine
            self.retrieval_engine = RetrievalEngine(self.embedding_service)
            await self.retrieval_engine.initialize()

            # Initialize knowledge graph
            self.knowledge_graph = KnowledgeGraph()
            await self.knowledge_graph.initialize()

            # Create default knowledge bases
            await self._create_default_knowledge_bases()

            # Load existing knowledge
            await self._load_existing_knowledge()

            self._initialized = True
            logger.info("Knowledge Management System initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Knowledge Manager initialization failed: {e}")
            return False

    async def _create_default_knowledge_bases(self) -> None:
        """Create default knowledge bases for different domains"""
        default_bases = [
            ("system", "System knowledge and documentation"),
            ("agents", "Agent capabilities and behaviors"),
            ("conversations", "Conversation history and patterns"),
            ("cultural", "Cultural knowledge and context"),
            ("technical", "Technical documentation and code"),
            ("user_preferences", "User preferences and settings"),
        ]

        for base_id, description in default_bases:
            if base_id not in self.knowledge_bases:
                kb = KnowledgeBase(base_id, description)
                await kb.initialize()
                self.knowledge_bases[base_id] = kb
                logger.debug(f"Created knowledge base: {base_id}")

    async def _load_existing_knowledge(self) -> None:
        """Load existing knowledge from persistent storage"""
        try:
            for kb_id, kb in self.knowledge_bases.items():
                await kb.load_from_storage()
                logger.debug(f"Loaded knowledge base: {kb_id}")

            await self._update_stats()

        except Exception as e:
            logger.warning(f"Error loading existing knowledge: {e}")

    async def add_knowledge(
        self,
        knowledge_base: str,
        content: str,
        knowledge_type: KnowledgeType,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        tags: list[str] | None = None,
        tenant_id: int | None = None,
    ) -> str | None:
        """
        Add new knowledge entry to specified knowledge base

        Args:
            knowledge_base: Target knowledge base ID
            content: Knowledge content (ASCII-only)
            knowledge_type: Type of knowledge entry
            metadata: Additional metadata
            tags: Knowledge tags for categorization

        Returns:
            Entry ID if successful, None if failed
        """
        if not self._initialized:
            await self.initialize()

        try:
            # Ensure ASCII compliance
            ascii_content = content.encode("ascii", errors="ignore").decode("ascii")

            if len(ascii_content) != len(content):
                logger.warning("Non-ASCII characters removed from knowledge content")

            # Get or create knowledge base
            if knowledge_base not in self.knowledge_bases:
                kb = KnowledgeBase(knowledge_base, f"Auto-created knowledge base: {knowledge_base}")
                await kb.initialize()
                self.knowledge_bases[knowledge_base] = kb

            kb = self.knowledge_bases[knowledge_base]

            # Create knowledge entry
            entry = KnowledgeEntry(
                content=ascii_content,
                knowledge_type=knowledge_type,
                metadata=metadata or {},
                tenant_id=tenant_id,
                tags=tags or [],
                created_at=datetime.now(timezone.utc),
            )

            # Add to knowledge base
            entry_id: str | None = await kb.add_entry(entry)

            if entry_id:
                # Generate embeddings for retrieval
                if self.embedding_service:
                    embedding = await self.embedding_service.generate_embedding(ascii_content)
                    if embedding and self.retrieval_engine:
                        await self.retrieval_engine.index_entry(entry_id, embedding, entry)

                # Add to knowledge graph if applicable
                if self.knowledge_graph and knowledge_type in [
                    KnowledgeType.FACTUAL,
                    KnowledgeType.CONCEPTUAL,
                ]:
                    await self.knowledge_graph.add_knowledge_entry(entry_id, entry)

                # Update statistics
                await self._update_stats()

                # Log operation
                self._log_operation(
                    "add_knowledge",
                    {
                        "knowledge_base": knowledge_base,
                        "entry_id": entry_id,
                        "type": knowledge_type.value,
                        "content_length": len(ascii_content),
                    },
                )

                logger.info(f"Added knowledge entry {entry_id} to {knowledge_base}")
                return entry_id

        except Exception as e:
            logger.error(f"Failed to add knowledge: {e}")
            self._log_operation(
                "add_knowledge_failed",
                {"knowledge_base": knowledge_base, "error": str(e)},
            )

        return None

    @cached(ttl=300, key_prefix="knowledge_search")
    async def search_knowledge(
        self,
        query: str,
        tenant_id: int,
        knowledge_bases: list[str] | None = None,
        knowledge_types: list[KnowledgeType] | None = None,
        limit: int = 10,
        similarity_threshold: float = 0.7,
    ) -> list[SearchResult]:
        """
        Search across knowledge bases using semantic similarity

        Args:
            query: Search query (ASCII-only)
            knowledge_bases: Specific knowledge bases to search (None for all)
            knowledge_types: Filter by knowledge types
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score

        Returns: List[Any] of search results sorted by relevance  # TODO(TYPE): replace Any with concrete type
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            # Ensure ASCII compliance
            ascii_query = query.encode("ascii", errors="ignore").decode("ascii")

            if not self.retrieval_engine:
                logger.warning("Retrieval engine not available")
                return []

            # Create search query
            search_query = SearchQuery(
                query=ascii_query,
                tenant_id=tenant_id,
                knowledge_bases=tuple(knowledge_bases) if knowledge_bases else None,
                knowledge_types=tuple(knowledge_types) if knowledge_types else None,
                limit=limit,
                similarity_threshold=similarity_threshold,
            )

            # Perform search
            results: list[SearchResult] = await self.retrieval_engine.search(search_query)

            # Update statistics
            search_time = time.time() - start_time
            self._update_retrieval_stats(search_time)

            # Log operation
            self._log_operation(
                "search_knowledge",
                {
                    "query": ascii_query,
                    "results_count": len(results),
                    "search_time": search_time,
                },
            )

            logger.debug(f"Search completed: {len(results)} results in {search_time:.3f}s")
            return results

        except Exception as e:
            logger.error(f"Knowledge search failed: {e}")
            self._log_operation("search_failed", {"query": query, "error": str(e)})
            return []

    async def get_knowledge_entry(
        self, knowledge_base: str, entry_id: str
    ) -> KnowledgeEntry | None:
        """Get specific knowledge entry by ID"""
        if not self._initialized:
            await self.initialize()

        try:
            if knowledge_base in self.knowledge_bases:
                return await self.knowledge_bases[knowledge_base].get_entry(entry_id)
        except Exception as e:
            logger.error(f"Failed to get knowledge entry {entry_id}: {e}")

        return None

    async def update_knowledge_entry(
        self,
        knowledge_base: str,
        entry_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        tags: list[str] | None = None,
    ) -> bool:
        """Update existing knowledge entry"""
        if not self._initialized:
            await self.initialize()

        try:
            if knowledge_base not in self.knowledge_bases:
                return False

            kb = self.knowledge_bases[knowledge_base]
            entry = await kb.get_entry(entry_id)

            if not entry:
                return False

            # Update fields
            if content is not None:
                ascii_content = content.encode("ascii", errors="ignore").decode("ascii")
                entry.content = ascii_content
                entry.updated_at = datetime.now(timezone.utc)

                # Update embeddings
                if self.embedding_service and self.retrieval_engine:
                    embedding = await self.embedding_service.generate_embedding(ascii_content)
                    if embedding:
                        await self.retrieval_engine.update_entry(entry_id, embedding, entry)

            if metadata is not None:
                entry.metadata.update(metadata)

            if tags is not None:
                entry.tags = tags

            # Save updated entry
            success: bool = await kb.update_entry(entry_id, entry)

            if success:
                await self._update_stats()
                self._log_operation(
                    "update_knowledge",
                    {"knowledge_base": knowledge_base, "entry_id": entry_id},
                )

            return success

        except Exception as e:
            logger.error(f"Failed to update knowledge entry {entry_id}: {e}")
            return False

    async def delete_knowledge_entry(self, knowledge_base: str, entry_id: str) -> bool:
        """Delete knowledge entry"""
        if not self._initialized:
            await self.initialize()

        try:
            if knowledge_base not in self.knowledge_bases:
                return False

            kb = self.knowledge_bases[knowledge_base]
            success: bool = await kb.delete_entry(entry_id)

            if success:
                # Remove from retrieval index
                if self.retrieval_engine:
                    await self.retrieval_engine.remove_entry(entry_id)

                # Remove from knowledge graph
                if self.knowledge_graph:
                    await self.knowledge_graph.remove_entry(entry_id)

                await self._update_stats()
                self._log_operation(
                    "delete_knowledge",
                    {"knowledge_base": knowledge_base, "entry_id": entry_id},
                )

            return success

        except Exception as e:
            logger.error(f"Failed to delete knowledge entry {entry_id}: {e}")
            return False

    async def get_related_knowledge(
        self, entry_id: str, limit: int = 5, similarity_threshold: float = 0.6
    ) -> list[SearchResult]:
        """Get knowledge entries related to a specific entry"""
        if not self._initialized or not self.knowledge_graph:
            return []

        try:
            related: list[SearchResult] = await self.knowledge_graph.get_related_entries(
                entry_id, limit, similarity_threshold
            )
            return related
        except Exception as e:
            logger.error(f"Failed to get related knowledge for {entry_id}: {e}")
            return []

    async def get_knowledge_stats(self) -> KnowledgeStats:
        """Get current knowledge system statistics"""
        if not self._initialized:
            await self.initialize()

        await self._update_stats()
        return self._stats

    async def _update_stats(self) -> None:
        """Update system statistics"""
        try:
            total_entries = 0
            entries_by_type: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for kb in self.knowledge_bases.values():
                stats = await kb.get_stats()
                total_entries += stats.get("total_entries", 0)

                for kt, count in stats.get("entries_by_type", {}).items():
                    entries_by_type[kt] = entries_by_type.get(kt, 0) + count

            self._stats.total_entries = total_entries
            self._stats.entries_by_type = entries_by_type
            self._stats.last_update = datetime.now(timezone.utc)

            # Get cache stats
            if cache_system:
                cache_stats = await cache_system.get_stats()
                self._stats.cache_hit_rate = float(cache_stats.get("hit_rate_percent", 0.0))  # type: ignore[arg-type]

        except Exception as e:
            logger.error(f"Failed to update knowledge stats: {e}")

    def _update_retrieval_stats(self, search_time: float) -> None:
        """Update retrieval performance statistics"""
        # Simple moving average for retrieval time
        if self._stats.avg_retrieval_time == 0:
            self._stats.avg_retrieval_time = search_time
        else:
            self._stats.avg_retrieval_time = (self._stats.avg_retrieval_time * 0.9) + (
                search_time * 0.1
            )

    def _log_operation(
        self,
        operation: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Log knowledge operations for audit and monitoring"""
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "details": details,
        }

        self._operation_history.append(log_entry)

        # Keep only last 1000 operations
        if len(self._operation_history) > 1000:
            self._operation_history = self._operation_history[-1000:]

    async def get_operation_history(
        self, limit: int = 100
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get recent operation history"""
        return self._operation_history[-limit:]

    async def optimize_knowledge_base(self, knowledge_base: str) -> bool:
        """Optimize specific knowledge base (rebuild indexes, cleanup)"""
        if not self._initialized:
            await self.initialize()

        try:
            if knowledge_base not in self.knowledge_bases:
                return False

            kb = self.knowledge_bases[knowledge_base]

            # Optimize knowledge base
            await kb.optimize()

            # Rebuild retrieval index for this knowledge base
            if self.retrieval_engine:
                await self.retrieval_engine.rebuild_index(knowledge_base)

            self._log_operation("optimize_knowledge_base", {"knowledge_base": knowledge_base})

            logger.info(f"Optimized knowledge base: {knowledge_base}")
            return True

        except Exception as e:
            logger.error(f"Failed to optimize knowledge base {knowledge_base}: {e}")
            return False

    async def backup_knowledge(self, backup_path: str) -> bool:
        """Backup all knowledge bases to specified path"""
        try:
            backup_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "knowledge_bases": {},
            }

            for kb_id, kb in self.knowledge_bases.items():
                backup_data["knowledge_bases"][kb_id] = await kb.export_data()

            # Save backup (implementation depends on storage backend)
            # For now, log the backup operation
            self._log_operation(
                "backup_knowledge",
                {
                    "backup_path": backup_path,
                    "knowledge_bases": list(self.knowledge_bases.keys()),
                },
            )

            logger.info(f"Knowledge backup completed to {backup_path}")
            return True

        except Exception as e:
            logger.error(f"Knowledge backup failed: {e}")
            return False


# Global knowledge manager instance
knowledge_manager = KnowledgeManager()
