"""
Embedding Versioning - Zero-downtime embedding model upgrades

Features:
- EmbeddingVersion model with version_id, model_name, dimensions, status
- Dual-read strategy during transition
- Background reindexing with progress tracking
- Activation only when 100% complete

Status lifecycle:
- BUILDING: Reindex in progress
- ACTIVE: Current version for writes
- DEPRECATED: Old version (dual-read only)
- ARCHIVED: No longer used
"""

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class EmbeddingVersionStatus(str, enum.Enum):
    """Status for embedding versions."""

    BUILDING = "building"  # Reindex in progress
    ACTIVE = "active"  # Current version
    DEPRECATED = "deprecated"  # Old version (dual-read)
    ARCHIVED = "archived"  # No longer used


@dataclass
class EmbeddingVersion:
    """Represents an embedding model version."""

    version_id: str
    model_name: str
    dimensions: int
    status: EmbeddingVersionStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: datetime | None = None
    reindex_progress: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "version_id": self.version_id,
            "model_name": self.model_name,
            "dimensions": self.dimensions,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "reindex_progress": self.reindex_progress,
        }


@dataclass
class ReindexProgress:
    """Tracks reindexing progress."""

    total_documents: int
    processed: int = 0
    failed: int = 0

    @property
    def percent_complete(self) -> float:
        """Calculate percentage complete."""
        if self.total_documents == 0:
            return 100.0
        return (self.processed / self.total_documents) * 100

    @property
    def is_complete(self) -> bool:
        """Check if reindexing is complete."""
        return self.processed >= self.total_documents


class EmbeddingVersionManager:
    """
    Manages embedding model versions with zero-downtime upgrades.

    Features:
    - Create new versions (status=BUILDING)
    - Track reindex progress
    - Activate when complete (status=ACTIVE, deprecate old)
    - Dual-read during transition
    """

    def __init__(self) -> None:
        """Initialize version manager."""
        self._versions: dict[str, EmbeddingVersion] = {}
        self._active_version_id: str | None = None
        self._reindex_tasks: dict[str, ReindexProgress] = {}

    def create_version(
        self,
        version_id: str,
        model_name: str,
        dimensions: int,
    ) -> EmbeddingVersion:
        """
        Create a new embedding version.

        Args:
            version_id: Unique version identifier
            model_name: Name of the embedding model
            dimensions: Vector dimensions

        Returns:
            New EmbeddingVersion with status=BUILDING
        """
        version = EmbeddingVersion(
            version_id=version_id,
            model_name=model_name,
            dimensions=dimensions,
            status=EmbeddingVersionStatus.BUILDING,
            reindex_progress={"total": 0, "processed": 0, "failed": 0},
        )

        self._versions[version_id] = version

        # Initialize reindex progress
        self._reindex_tasks[version_id] = ReindexProgress(total_documents=0)

        logger.info(f"Created embedding version {version_id} with model {model_name}")
        return version

    def start_reindex(self, version_id: str, total_documents: int) -> None:
        """
        Start reindexing for a version.

        Args:
            version_id: Version to reindex
            total_documents: Total documents to process
        """
        if version_id not in self._versions:
            raise ValueError(f"Version {version_id} not found")

        self._reindex_tasks[version_id] = ReindexProgress(total_documents=total_documents)

        logger.info(f"Started reindex for version {version_id}: {total_documents} documents")

    def update_reindex_progress(
        self,
        version_id: str,
        processed: int,
        failed: int = 0,
    ) -> None:
        """
        Update reindex progress.

        Args:
            version_id: Version being reindexed
            processed: Documents processed so far
            failed: Documents that failed
        """
        if version_id not in self._reindex_tasks:
            raise ValueError(f"No reindex task for version {version_id}")

        task = self._reindex_tasks[version_id]
        task.processed = processed
        task.failed = failed

        # Update version progress
        version = self._versions[version_id]
        version.reindex_progress = {
            "total": task.total_documents,
            "processed": processed,
            "failed": failed,
            "percent": task.percent_complete,
        }

        logger.debug(f"Reindex progress for {version_id}: {task.percent_complete:.1f}%")

    def activate_version(self, version_id: str) -> None:
        """
        Activate a version (only when 100% reindexed).

        Args:
            version_id: Version to activate

        Raises:
            ValueError: If reindex not complete or version not found
        """
        if version_id not in self._versions:
            raise ValueError(f"Version {version_id} not found")

        version = self._versions[version_id]

        # Check if reindex is complete
        if version_id in self._reindex_tasks:
            task = self._reindex_tasks[version_id]
            if not task.is_complete:
                raise ValueError(
                    f"Cannot activate {version_id}: reindex incomplete "
                    f"({task.percent_complete:.1f}%)"
                )

        # Deprecate current active version
        if self._active_version_id:
            old_version = self._versions[self._active_version_id]
            old_version.status = EmbeddingVersionStatus.DEPRECATED
            logger.info(f"Deprecated version {self._active_version_id}")

        # Activate new version
        version.status = EmbeddingVersionStatus.ACTIVE
        version.activated_at = datetime.now(timezone.utc)
        self._active_version_id = version_id

        logger.info(f"Activated version {version_id}")

    def get_active_version(self) -> EmbeddingVersion | None:
        """Get currently active version."""
        if self._active_version_id:
            return self._versions.get(self._active_version_id)
        return None

    def get_dual_read_versions(self) -> list[EmbeddingVersion]:
        """
        Get versions for dual-read strategy.

        Returns: List[Any] of versions to search (ACTIVE + DEPRECATED)  # TODO(TYPE): replace Any with concrete type
        """
        dual_read: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for version in self._versions.values():
            if version.status in (
                EmbeddingVersionStatus.ACTIVE,
                EmbeddingVersionStatus.DEPRECATED,
            ):
                dual_read.append(version)
        return dual_read

    def get_version(self, version_id: str) -> EmbeddingVersion | None:
        """Get version by ID."""
        return self._versions.get(version_id)

    def list_versions(self) -> list[EmbeddingVersion]:
        """List all versions."""
        return list(self._versions.values())

    def archive_version(self, version_id: str) -> None:
        """
        Archive a deprecated version.

        Args:
            version_id: Version to archive
        """
        if version_id not in self._versions:
            raise ValueError(f"Version {version_id} not found")

        version = self._versions[version_id]
        if version.status != EmbeddingVersionStatus.DEPRECATED:
            raise ValueError(f"Cannot archive {version_id}: must be DEPRECATED first")

        version.status = EmbeddingVersionStatus.ARCHIVED
        logger.info(f"Archived version {version_id}")


# Singleton instance
_version_manager_instance: EmbeddingVersionManager | None = None


def get_version_manager() -> EmbeddingVersionManager:
    """Get singleton EmbeddingVersionManager."""
    global _version_manager_instance
    if _version_manager_instance is None:
        _version_manager_instance = EmbeddingVersionManager()
    return _version_manager_instance
