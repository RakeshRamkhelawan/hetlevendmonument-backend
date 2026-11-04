"""
Knowledge Base - Storage and management of knowledge entries
Implements efficient storage, indexing, and retrieval of knowledge
"""

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class KnowledgeType(Enum):
    """Types of knowledge entries"""

    FACTUAL = "factual"
    PROCEDURAL = "procedural"
    CONCEPTUAL = "conceptual"
    EXPERIENTIAL = "experiential"
    CONVERSATIONAL = "conversational"
    CULTURAL = "cultural"
    TECHNICAL = "technical"
    USER_PREFERENCE = "user_preference"


@dataclass
class KnowledgeEntry:
    """Individual knowledge entry with metadata"""

    content: str
    knowledge_type: KnowledgeType
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None = None
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None
    entry_id: str | None = None
    source: str | None = None
    confidence: float = 1.0
    version: int = 1

    def __post_init__(self) -> None:
        if self.entry_id is None:
            self.entry_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate unique entry ID"""
        content_hash = hashlib.md5(
            f"{self.content}{self.created_at.isoformat()}".encode("ascii", errors="ignore"),
            usedforsecurity=False,
        ).hexdigest()[:8]
        return f"ke_{content_hash}_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["knowledge_type"] = self.knowledge_type.value
        data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeEntry":  # TODO(TYPE): replace Any with concrete type
        """Create instance from dictionary"""
        # Parse datetime fields
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        if data.get("updated_at"):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])

        # Parse enum
        data["knowledge_type"] = KnowledgeType(data["knowledge_type"])

        return cls(**data)


class KnowledgeBase:
    """
    Knowledge base for storing and managing knowledge entries
    Supports multiple storage backends and efficient querying
    """

    def __init__(self, base_id: str, description: str) -> None:
        self.base_id = base_id
        self.description = description
        self.entries: dict[str, KnowledgeEntry] = {}
        self.tags_index: dict[str, set[str]] = {}  # tag -> set of entry_ids
        self.type_index: dict[KnowledgeType, set[str]] = {}  # type -> set of entry_ids
        self.content_index: dict[str, set[str]] = {}  # word -> set of entry_ids
        self._initialized = False
        self._dirty = False  # Track if changes need to be persisted

    async def initialize(self) -> bool:
        """Initialize knowledge base"""
        try:
            self._build_indexes()
            self._initialized = True
            logger.info(f"Knowledge base '{self.base_id}' initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize knowledge base '{self.base_id}': {e}")
            return False

    async def add_entry(self, entry: KnowledgeEntry) -> str | None:
        """
        Add new knowledge entry

        Args:
            entry: Knowledge entry to add

        Returns:
            Entry ID if successful, None if failed
        """
        try:
            if not entry.entry_id:
                entry.entry_id = entry._generate_id()

            # Check for duplicates
            if await self._is_duplicate(entry):
                logger.warning(f"Duplicate entry detected: {entry.content[:50]}...")
                return None

            # Store entry
            self.entries[entry.entry_id] = entry

            # Update indexes
            self._update_indexes_add(entry)

            # Mark as dirty for persistence
            self._dirty = True

            logger.debug(f"Added knowledge entry: {entry.entry_id}")
            return entry.entry_id

        except Exception as e:
            logger.error(f"Failed to add knowledge entry: {e}")
            return None

    async def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """Get knowledge entry by ID"""
        return self.entries.get(entry_id)

    async def update_entry(self, entry_id: str, entry: KnowledgeEntry) -> bool:
        """Update existing knowledge entry"""
        try:
            if entry_id not in self.entries:
                return False

            old_entry = self.entries[entry_id]

            # Update indexes (remove old, add new)
            self._update_indexes_remove(old_entry)
            self._update_indexes_add(entry)

            # Update entry
            entry.entry_id = entry_id
            entry.version = old_entry.version + 1
            entry.updated_at = datetime.now(timezone.utc)
            self.entries[entry_id] = entry

            self._dirty = True
            logger.debug(f"Updated knowledge entry: {entry_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update knowledge entry {entry_id}: {e}")
            return False

    async def delete_entry(self, entry_id: str) -> bool:
        """Delete knowledge entry"""
        try:
            if entry_id not in self.entries:
                return False

            entry = self.entries[entry_id]

            # Remove from indexes
            self._update_indexes_remove(entry)

            # Delete entry
            del self.entries[entry_id]

            self._dirty = True
            logger.debug(f"Deleted knowledge entry: {entry_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete knowledge entry {entry_id}: {e}")
            return False

    async def search_by_tags(self, tags: list[str], operator: str = "OR") -> list[KnowledgeEntry]:
        """Search entries by tags"""
        try:
            if not tags:
                return []

            if operator.upper() == "AND":
                # All tags must be present
                matching_ids = None
                for tag in tags:
                    tag_ids = self.tags_index.get(tag.lower(), set())
                    if matching_ids is None:
                        matching_ids = tag_ids.copy()
                    else:
                        matching_ids = matching_ids.intersection(tag_ids)

                    if not matching_ids:
                        break
            else:
                # Any tag must be present (OR)
                matching_ids = set()
                for tag in tags:
                    tag_ids = self.tags_index.get(tag.lower(), set())
                    if tag_ids is not None:
                        matching_ids = matching_ids.union(tag_ids)

            # Ensure matching_ids is a set (it could be None if AND operator with no matches)
            if matching_ids is None:
                matching_ids = set()

            return [self.entries[entry_id] for entry_id in matching_ids if entry_id in self.entries]

        except Exception as e:
            logger.error(f"Failed to search by tags: {e}")
            return []

    async def search_by_type(self, knowledge_type: KnowledgeType) -> list[KnowledgeEntry]:
        """Search entries by knowledge type"""
        try:
            entry_ids = self.type_index.get(knowledge_type, set())
            return [self.entries[entry_id] for entry_id in entry_ids if entry_id in self.entries]
        except Exception as e:
            logger.error(f"Failed to search by type: {e}")
            return []

    async def search_content(self, query: str, limit: int = 50) -> list[KnowledgeEntry]:
        """
        Simple content search using word matching
        For advanced semantic search, use RetrievalEngine
        """
        try:
            # Ensure ASCII query
            ascii_query = query.encode("ascii", errors="ignore").decode("ascii").lower()
            query_words = set(ascii_query.split())

            if not query_words:
                return []

            # Find entries containing query words
            matching_ids: set[str] = set()
            for word in query_words:
                word_ids = self.content_index.get(word, set())
                matching_ids = matching_ids.union(word_ids)

            # Sort by relevance (number of matching words)
            entries_with_score: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for entry_id in matching_ids:
                if entry_id in self.entries:
                    entry = self.entries[entry_id]
                    content_words = set(entry.content.lower().split())
                    score = len(query_words.intersection(content_words))
                    entries_with_score.append((score, entry))

            # Sort by score descending
            entries_with_score.sort(key=lambda x: x[0], reverse=True)

            return [entry for _, entry in entries_with_score[:limit]]

        except Exception as e:
            logger.error(f"Failed to search content: {e}")
            return []

    async def get_entries_by_date_range(
        self, start_date: datetime, end_date: datetime
    ) -> list[KnowledgeEntry]:
        """Get entries created within date range"""
        try:
            matching_entries: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for entry in self.entries.values():
                if start_date <= entry.created_at <= end_date:
                    matching_entries.append(entry)

            # Sort by creation date
            matching_entries.sort(key=lambda x: x.created_at, reverse=True)
            return matching_entries

        except Exception as e:
            logger.error(f"Failed to get entries by date range: {e}")
            return []

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get knowledge base statistics"""
        try:
            entries_by_type: dict[str, int] = {}
            stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "base_id": self.base_id,
                "description": self.description,
                "total_entries": len(self.entries),
                "entries_by_type": entries_by_type,
                "total_tags": len(self.tags_index),
                "most_common_tags": [],
                "latest_entry": None,
                "oldest_entry": None,
            }

            # Count entries by type
            for knowledge_type, entry_ids in self.type_index.items():
                entries_by_type[knowledge_type.value] = len(entry_ids)

            # Find most common tags
            tag_counts = [(tag, len(entry_ids)) for tag, entry_ids in self.tags_index.items()]
            tag_counts.sort(key=lambda x: x[1], reverse=True)
            stats["most_common_tags"] = tag_counts[:10]

            # Find date range
            if self.entries:
                entries_by_date = sorted(self.entries.values(), key=lambda x: x.created_at)
                stats["oldest_entry"] = entries_by_date[0].created_at.isoformat()
                stats["latest_entry"] = entries_by_date[-1].created_at.isoformat()

            return stats

        except Exception as e:
            logger.error(f"Failed to get knowledge base stats: {e}")
            return {}

    async def export_data(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Export all knowledge base data"""
        try:
            return {
                "base_id": self.base_id,
                "description": self.description,
                "entries": [entry.to_dict() for entry in self.entries.values()],
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to export knowledge base data: {e}")
            return {}

    async def import_data(self, data: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Import knowledge base data"""
        try:
            if "entries" not in data:
                return False

            imported_count = 0
            for entry_data in data["entries"]:
                try:
                    entry = KnowledgeEntry.from_dict(entry_data)
                    if await self.add_entry(entry):
                        imported_count += 1
                except Exception as e:
                    logger.warning(f"Failed to import entry: {e}")

            logger.info(f"Imported {imported_count} entries to knowledge base '{self.base_id}'")
            return True

        except Exception as e:
            logger.error(f"Failed to import knowledge base data: {e}")
            return False

    async def optimize(self) -> None:
        """Optimize knowledge base (rebuild indexes, cleanup)"""
        try:
            # Rebuild all indexes
            self._build_indexes()

            # Remove orphaned index entries
            self._cleanup_indexes()

            logger.info(f"Optimized knowledge base '{self.base_id}'")

        except Exception as e:
            logger.error(f"Failed to optimize knowledge base: {e}")

    async def load_from_storage(self) -> None:
        """Load knowledge base from persistent storage"""
        # Implementation depends on storage backend
        # For now, this is a placeholder
        logger.debug(f"Loading knowledge base '{self.base_id}' from storage")

    async def save_to_storage(self) -> None:
        """Save knowledge base to persistent storage"""
        if not self._dirty:
            return

        # Implementation depends on storage backend
        # For now, this is a placeholder
        self._dirty = False
        logger.debug(f"Saved knowledge base '{self.base_id}' to storage")

    def _build_indexes(self) -> None:
        """Build search indexes for efficient querying"""
        self.tags_index.clear()
        self.type_index.clear()
        self.content_index.clear()

        for entry in self.entries.values():
            self._update_indexes_add(entry)

    def _update_indexes_add(self, entry: KnowledgeEntry) -> None:
        """Update indexes when adding entry"""
        if not entry.entry_id:
            return

        # Tags index
        for tag in entry.tags:
            tag_lower = tag.lower()
            if tag_lower not in self.tags_index:
                self.tags_index[tag_lower] = set()
            self.tags_index[tag_lower].add(entry.entry_id)

        # Type index
        if entry.knowledge_type not in self.type_index:
            self.type_index[entry.knowledge_type] = set()
        self.type_index[entry.knowledge_type].add(entry.entry_id)

        # Content index (simple word-based)
        content_words = entry.content.lower().split()
        for word in content_words:
            # Clean word (remove punctuation, ensure ASCII)
            clean_word = (
                "".join(c for c in word if c.isalnum())
                .encode("ascii", errors="ignore")
                .decode("ascii")
            )
            if len(clean_word) > 2:  # Ignore very short words
                if clean_word not in self.content_index:
                    self.content_index[clean_word] = set()
                self.content_index[clean_word].add(entry.entry_id)

    def _update_indexes_remove(self, entry: KnowledgeEntry) -> None:
        """Update indexes when removing entry"""
        if not entry.entry_id:
            return

        # Tags index
        for tag in entry.tags:
            tag_lower = tag.lower()
            if tag_lower in self.tags_index:
                self.tags_index[tag_lower].discard(entry.entry_id)
                if not self.tags_index[tag_lower]:
                    del self.tags_index[tag_lower]

        # Type index
        if entry.knowledge_type in self.type_index:
            self.type_index[entry.knowledge_type].discard(entry.entry_id)
            if not self.type_index[entry.knowledge_type]:
                del self.type_index[entry.knowledge_type]

        # Content index
        content_words = entry.content.lower().split()
        for word in content_words:
            clean_word = (
                "".join(c for c in word if c.isalnum())
                .encode("ascii", errors="ignore")
                .decode("ascii")
            )
            if clean_word in self.content_index:
                self.content_index[clean_word].discard(entry.entry_id)
                if not self.content_index[clean_word]:
                    del self.content_index[clean_word]

    def _cleanup_indexes(self) -> None:
        """Remove orphaned index entries"""
        valid_entry_ids = set(self.entries.keys())

        # Clean tags index
        for tag in list(self.tags_index.keys()):
            self.tags_index[tag] = self.tags_index[tag].intersection(valid_entry_ids)
            if not self.tags_index[tag]:
                del self.tags_index[tag]

        # Clean type index
        for knowledge_type in list(self.type_index.keys()):
            self.type_index[knowledge_type] = self.type_index[knowledge_type].intersection(
                valid_entry_ids
            )
            if not self.type_index[knowledge_type]:
                del self.type_index[knowledge_type]

        # Clean content index
        for word in list(self.content_index.keys()):
            self.content_index[word] = self.content_index[word].intersection(valid_entry_ids)
            if not self.content_index[word]:
                del self.content_index[word]

    async def _is_duplicate(self, entry: KnowledgeEntry) -> bool:
        """Check if entry is a duplicate"""
        # Simple duplicate detection based on content similarity
        content_hash = hashlib.md5(
            entry.content.encode("ascii", errors="ignore"), usedforsecurity=False
        ).hexdigest()

        for existing_entry in self.entries.values():
            existing_hash = hashlib.md5(
                existing_entry.content.encode("ascii", errors="ignore"),
                usedforsecurity=False,
            ).hexdigest()
            if content_hash == existing_hash:
                return True

        return False
