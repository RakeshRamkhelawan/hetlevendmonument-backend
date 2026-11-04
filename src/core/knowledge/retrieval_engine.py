"""
Retrieval Engine - Semantic search and retrieval for knowledge entries
Implements vector-based similarity search with caching
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, cast

import numpy as np

from src.core.caching.cache_layer import cached
from src.core.observability.metrics import SEARCH_CROSS_TENANT_LEAKAGE_DETECTED_TOTAL
from src.core.shared.production_logging import SafeLogger

from .embedding_service import EmbeddingService
from .knowledge_base import KnowledgeEntry, KnowledgeType

logger = SafeLogger(__name__)


@dataclass(frozen=True)
class SearchQuery:
    """Search query configuration"""

    query: str
    tenant_id: int | None = None
    knowledge_bases: tuple[str, ...] | None = None  # Changed List to Tuple for hashing
    knowledge_types: tuple[KnowledgeType, ...] | None = None  # Changed List to Tuple for hashing
    limit: int = 10
    similarity_threshold: float = 0.7
    boost_recent: bool = False
    boost_factor: float = 1.2


@dataclass
class SearchResult:
    """Search result with relevance scoring"""

    entry_id: str
    entry: KnowledgeEntry
    similarity_score: float
    relevance_score: float
    knowledge_base: str
    matched_content: str = ""

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization"""
        return {
            "entry_id": self.entry_id,
            "entry": self.entry.to_dict(),
            "similarity_score": self.similarity_score,
            "relevance_score": self.relevance_score,
            "knowledge_base": self.knowledge_base,
            "matched_content": self.matched_content,
        }


class VectorIndex:
    """In-memory vector index for fast similarity search"""

    def __init__(self) -> None:
        self.vectors: dict[str, np.ndarray[Any, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.metadata: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.dimension: int | None = None

    def add_vector(
        self, entry_id: str, vector: np.ndarray[Any, Any], metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Add vector to index"""
        if self.dimension is None:
            self.dimension = len(vector)
        elif len(vector) != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {len(vector)}"
            )

        self.vectors[entry_id] = vector
        self.metadata[entry_id] = metadata

    def update_vector(
        self, entry_id: str, vector: np.ndarray[Any, Any], metadata: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Update existing vector"""
        self.add_vector(entry_id, vector, metadata)

    def remove_vector(self, entry_id: str) -> None:
        """Remove vector from index"""
        if entry_id in self.vectors:
            del self.vectors[entry_id]
        if entry_id in self.metadata:
            del self.metadata[entry_id]

    def search(
        self, query_vector: np.ndarray[Any, Any], limit: int = 10, threshold: float = 0.7  # TODO(TYPE): replace Any with concrete type
    ) -> list[tuple[str, float]]:
        """Search for similar vectors using cosine similarity"""
        if not self.vectors or len(query_vector) != self.dimension:
            return []

        similarities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for entry_id, vector in self.vectors.items():
            # Cosine similarity
            similarity = np.dot(query_vector, vector) / (
                np.linalg.norm(query_vector) * np.linalg.norm(vector)
            )

            if similarity >= threshold:
                similarities.append((entry_id, float(similarity)))

        # Sort by similarity descending
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:limit]

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get index statistics"""
        return {
            "total_vectors": len(self.vectors),
            "dimension": self.dimension,
            "memory_usage_mb": sum(v.nbytes for v in self.vectors.values()) / (1024 * 1024),
        }


class RetrievalEngine:
    """
    Semantic retrieval engine for knowledge entries
    Uses embeddings for similarity search with advanced relevance scoring
    """

    def __init__(self, embedding_service: EmbeddingService) -> None:
        self.embedding_service = embedding_service
        self.indexes: dict[str, VectorIndex] = {}  # knowledge_base -> VectorIndex
        self.global_index = VectorIndex()  # Combined index for cross-base search
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize retrieval engine"""
        try:
            if not self.embedding_service:
                logger.error("Embedding service required for retrieval engine")
                return False

            self._initialized = True
            logger.info("Retrieval engine initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize retrieval engine: {e}")
            return False

    async def index_entry(
        self,
        entry_id: str,
        embedding: np.ndarray[Any, Any],  # TODO(TYPE): replace Any with concrete type
        entry: KnowledgeEntry,
        knowledge_base: str = "default",
    ) -> bool:
        """Add entry to vector index"""
        if not self._initialized:
            return False

        try:
            # Metadata for search filtering
            metadata = {
                "knowledge_base": knowledge_base,
                "knowledge_type": entry.knowledge_type.value,
                "tags": entry.tags,
                "created_at": entry.created_at.isoformat(),
                "content_length": len(entry.content),
                "confidence": entry.confidence,
                "tenant_id": entry.tenant_id,
            }

            # Add to knowledge base specific index
            if knowledge_base not in self.indexes:
                self.indexes[knowledge_base] = VectorIndex()

            self.indexes[knowledge_base].add_vector(entry_id, embedding, metadata)

            # Add to global index
            metadata["knowledge_base"] = knowledge_base
            self.global_index.add_vector(entry_id, embedding, metadata)

            logger.debug(f"Indexed entry {entry_id} in knowledge base {knowledge_base}")
            return True

        except Exception as e:
            logger.error(f"Failed to index entry {entry_id}: {e}")
            return False

    async def update_entry(
        self,
        entry_id: str,
        embedding: np.ndarray[Any, Any],  # TODO(TYPE): replace Any with concrete type
        entry: KnowledgeEntry,
        knowledge_base: str = "default",
    ) -> bool:
        """Update existing entry in index"""
        return await self.index_entry(entry_id, embedding, entry, knowledge_base)

    async def remove_entry(self, entry_id: str, knowledge_base: str | None = None) -> None:
        """Remove entry from index"""
        try:
            # Remove from global index
            self.global_index.remove_vector(entry_id)

            # Remove from specific knowledge base index
            if knowledge_base and knowledge_base in self.indexes:
                self.indexes[knowledge_base].remove_vector(entry_id)
            else:
                # Remove from all indexes if knowledge base not specified
                for index in self.indexes.values():
                    index.remove_vector(entry_id)

            logger.debug(f"Removed entry {entry_id} from indexes")

        except Exception as e:
            logger.error(f"Failed to remove entry {entry_id}: {e}")

    @cached(ttl=300, key_prefix="retrieval_search")
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        Perform semantic search across knowledge bases

        Args:
            query: Search query configuration

        Returns: list[Any] of search results sorted by relevance  # TODO(TYPE): replace Any with concrete type
        """
        if not self._initialized:
            return []

        try:
            # Validate tenant_id is provided
            if query.tenant_id is None:
                raise ValueError("tenant_id is required for search")

            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(query.query)
            if query_embedding is None:
                logger.warning("Failed to generate query embedding")
                return []

            # Determine which indexes to search
            indexes_to_search: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            if query.knowledge_bases:
                for kb in query.knowledge_bases:
                    if kb in self.indexes:
                        indexes_to_search.append((kb, self.indexes[kb]))
            else:
                # Search global index
                indexes_to_search = [("global", self.global_index)]

            # Perform vector search
            all_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for kb_name, index in indexes_to_search:
                vector_results = index.search(
                    query_embedding,
                    limit=query.limit * 2,  # Get more candidates for filtering
                    threshold=query.similarity_threshold,
                )

                for entry_id, similarity in vector_results:
                    metadata = index.metadata.get(entry_id, {})

                    # Tenant isolation check
                    result_tenant_id = metadata.get("tenant_id")
                    if result_tenant_id is None:
                        # Legacy data without tenant_id - filter out for safety
                        continue
                    if result_tenant_id != query.tenant_id:
                        SEARCH_CROSS_TENANT_LEAKAGE_DETECTED_TOTAL.labels(source="vector").inc()
                        logger.critical(
                            f"Cross-tenant leak detected: result tenant={result_tenant_id}, "
                            f"query tenant={query.tenant_id}"
                        )
                        continue

                    # Apply filters
                    if not self._passes_filters(metadata, query):
                        continue

                    # Calculate relevance score
                    relevance_score = self._calculate_relevance_score(similarity, metadata, query)

                    all_results.append(
                        {
                            "entry_id": entry_id,
                            "similarity_score": similarity,
                            "relevance_score": relevance_score,
                            "knowledge_base": metadata.get("knowledge_base", kb_name),
                            "metadata": metadata,
                        }
                    )

            # Sort by relevance score
            all_results.sort(key=lambda x: x["relevance_score"], reverse=True)

            # Convert to SearchResult objects (need to fetch actual entries)
            search_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for result in all_results[: query.limit]:
                # Note: In a full implementation, we'd fetch the actual KnowledgeEntry
                # For now, we create a placeholder
                placeholder_entry = KnowledgeEntry(
                    content=f"Entry {result['entry_id']}",
                    knowledge_type=KnowledgeType.FACTUAL,
                    metadata=result["metadata"],
                    tags=[],
                    created_at=datetime.now(timezone.utc),
                )

                search_result = SearchResult(
                    entry_id=result["entry_id"],
                    entry=placeholder_entry,
                    similarity_score=result["similarity_score"],
                    relevance_score=result["relevance_score"],
                    knowledge_base=result["knowledge_base"],
                )
                search_results.append(search_result)

            logger.debug(
                f"Search completed: {len(search_results)} results for query '{query.query}'"
            )
            return search_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _passes_filters(self, metadata: dict[str, Any], query: SearchQuery) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Check if entry passes query filters"""
        # Filter by knowledge type
        if query.knowledge_types:
            entry_type = metadata.get("knowledge_type")
            if entry_type not in [kt.value for kt in query.knowledge_types]:
                return False

        return True

    def _calculate_relevance_score(
        self, similarity: float, metadata: dict[str, Any], query: SearchQuery  # TODO(TYPE): replace Any with concrete type
    ) -> float:
        """Calculate relevance score combining similarity and other factors"""
        relevance = similarity

        # Boost recent entries if requested
        if query.boost_recent:
            try:
                created_at = datetime.fromisoformat(metadata.get("created_at", ""))
                days_old = (datetime.now(timezone.utc) - created_at).days
                recency_boost = max(0, 1 - (days_old / 365))  # Boost decreases over a year
                relevance *= 1 + recency_boost * 0.2  # Up to 20% boost
            except Exception as e:
                logger.debug(
                    f"Failed to apply recency boost to relevance score: {str(e)}",
                    exc_info=False,
                )

        # Boost based on confidence
        confidence = metadata.get("confidence", 1.0)
        relevance *= confidence

        # Boost based on content length (longer content might be more comprehensive)
        content_length = metadata.get("content_length", 0)
        if content_length > 100:
            length_boost = min(0.1, content_length / 10000)  # Up to 10% boost
            relevance *= 1 + length_boost

        return cast(float, relevance)

    async def get_similar_entries(self, entry_id: str, limit: int = 5) -> list[SearchResult]:
        """Find entries similar to a given entry"""
        try:
            # Get the entry's vector from index
            entry_vector = None

            # Search in all indexes for the entry
            for index in [self.global_index] + list(self.indexes.values()):
                if entry_id in index.vectors:
                    entry_vector = index.vectors[entry_id]
                    index.metadata[entry_id]
                    break

            if entry_vector is None:
                return []

            # Search for similar vectors
            similar_results = self.global_index.search(
                entry_vector,
                limit=limit + 1,  # +1 because the entry itself will be included
                threshold=0.5,
            )

            # Filter out the original entry and convert to SearchResult
            search_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for similar_entry_id, similarity in similar_results:
                if similar_entry_id != entry_id:
                    metadata = self.global_index.metadata.get(similar_entry_id, {})

                    # Create placeholder entry
                    placeholder_entry = KnowledgeEntry(
                        content=f"Entry {similar_entry_id}",
                        knowledge_type=KnowledgeType.FACTUAL,
                        metadata=metadata,
                        tags=[],
                        created_at=datetime.now(timezone.utc),
                    )

                    search_result = SearchResult(
                        entry_id=similar_entry_id,
                        entry=placeholder_entry,
                        similarity_score=similarity,
                        relevance_score=similarity,
                        knowledge_base=metadata.get("knowledge_base", "unknown"),
                    )
                    search_results.append(search_result)

            return search_results[:limit]

        except Exception as e:
            logger.error(f"Failed to get similar entries for {entry_id}: {e}")
            return []

    async def rebuild_index(self, knowledge_base: str | None = None) -> None:
        """Rebuild vector index for optimization"""
        try:
            if knowledge_base:
                if knowledge_base in self.indexes:
                    # Clear specific knowledge base index
                    self.indexes[knowledge_base] = VectorIndex()
                    logger.info(f"Rebuilt index for knowledge base: {knowledge_base}")
            else:
                # Clear all indexes
                self.indexes.clear()
                self.global_index = VectorIndex()
                logger.info("Rebuilt all vector indexes")

        except Exception as e:
            logger.error(f"Failed to rebuild index: {e}")

    async def get_index_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get indexing statistics"""
        try:
            kb_indexes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "global_index": self.global_index.get_stats(),
                "knowledge_base_indexes": kb_indexes,
                "total_entries": 0,
            }

            for kb_name, index in self.indexes.items():
                kb_indexes[kb_name] = index.get_stats()
                stats["total_entries"] += index.get_stats()["total_vectors"]

            return stats

        except Exception as e:
            logger.error(f"Failed to get index stats: {e}")
            return {}

    async def optimize_indexes(self) -> None:
        """Optimize indexes for better performance"""
        try:
            # Remove empty indexes
            empty_indexes = [kb for kb, index in self.indexes.items() if not index.vectors]
            for kb in empty_indexes:
                del self.indexes[kb]

            logger.info("Optimized vector indexes")

        except Exception as e:
            logger.error(f"Failed to optimize indexes: {e}")

    async def export_index(self, knowledge_base: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Export index data for backup"""
        try:
            if knowledge_base and knowledge_base in self.indexes:
                index = self.indexes[knowledge_base]
                return {
                    "knowledge_base": knowledge_base,
                    "vectors": {
                        entry_id: vector.tolist() for entry_id, vector in index.vectors.items()
                    },
                    "metadata": index.metadata,
                    "dimension": index.dimension,
                }
            else:
                # Export global index
                return {
                    "knowledge_base": "global",
                    "vectors": {
                        entry_id: vector.tolist()
                        for entry_id, vector in self.global_index.vectors.items()
                    },
                    "metadata": self.global_index.metadata,
                    "dimension": self.global_index.dimension,
                }

        except Exception as e:
            logger.error(f"Failed to export index: {e}")
            return {}

    async def import_index(self, index_data: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Import index data from backup"""
        try:
            knowledge_base = index_data.get("knowledge_base", "default")
            vectors_data = index_data.get("vectors", {})
            metadata = index_data.get("metadata", {})
            dimension = index_data.get("dimension")

            if not vectors_data or not dimension:
                return False

            # Create new index
            if knowledge_base == "global":
                index = self.global_index
            else:
                index = VectorIndex()
                self.indexes[knowledge_base] = index

            # Import vectors
            for entry_id, vector_list in vectors_data.items():
                vector = np.array(vector_list)
                entry_metadata = metadata.get(entry_id, {})
                index.add_vector(entry_id, vector, entry_metadata)

            logger.info(f"Imported index for knowledge base: {knowledge_base}")
            return True

        except Exception as e:
            logger.error(f"Failed to import index: {e}")
            return False
