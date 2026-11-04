"""Cleanup Service for managing memory lifecycle."""

import logging
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CleanupService:
    """Service for cleaning up old memories based on age and importance."""

    def __init__(
        self,
        max_memories: dict[str, int] | None = None,
        importance_threshold: float = 0.8,
    ) -> None:
        self.max_memories = max_memories or {
            "strategic": 1000,
            "tactical": 5000,
            "episodic": 10000,
        }
        self.importance_threshold = importance_threshold

    def filter_by_age_and_importance(
        self,
        memories: list[T],
        cutoff_date: datetime,
        get_timestamp_func: Callable[[T], datetime],
        get_importance_func: Callable[[T], float],
    ) -> list[T]:
        """Filter memories to keep based on age and importance.

        Keeps memories that are either:
        - Newer than the cutoff date
        - Have importance score above threshold
        """
        return [
            mem
            for mem in memories
            if get_timestamp_func(mem) > cutoff_date
            or get_importance_func(mem) >= self.importance_threshold
        ]

    def calculate_cleanup_stats(
        self, original: list[T], cleaned: list[T], memory_type: str
    ) -> dict[str, str | int | float]:
        """Calculate cleanup statistics."""
        removed = len(original) - len(cleaned)
        return {
            "memory_type": memory_type,
            "original_count": len(original),
            "retained_count": len(cleaned),
            "removed_count": removed,
            "retention_rate": len(cleaned) / len(original) if original else 1.0,
        }

    def enforce_size_limit(self, memories: list[T], memory_type: str) -> list[T]:
        """Enforce size limit by keeping the most recent memories.

        Assumes ``memories`` is already ordered from oldest to newest.
        Callers must pre-sort by timestamp before calling this method.
        """
        limit = self.max_memories.get(memory_type, 1000)
        if len(memories) <= limit:
            return memories

        return memories[-limit:]

    async def cleanup_old_memories(
        self,
        memories: dict[str, list[T]],
        days_old: int = 30,
        get_timestamp_func: Callable[[T], datetime] | None = None,
        get_importance_func: Callable[[T], float] | None = None,
    ) -> dict[str, dict[str, int]]:
        """Clean up old memories across all memory types.

        Args:
            memories: mapping memory type to list of memories
            days_old: Age threshold in days
            get_timestamp_func: Function to extract timestamp from memory
            get_importance_func: Function to extract importance from memory

        Returns: cleanup statistics for each memory type
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)
        results: dict[str, dict[str, int]] = {}
        for memory_type, memory_list in memories.items():
            if not memory_list:
                results[memory_type] = {
                    "original_count": 0,
                    "retained_count": 0,
                    "removed_count": 0,
                }
                continue

            original_count = len(memory_list)

            # Filter by age and importance
            if get_timestamp_func and get_importance_func:
                filtered = self.filter_by_age_and_importance(
                    memory_list,
                    cutoff_date,
                    get_timestamp_func,
                    get_importance_func,
                )
            else:
                filtered = memory_list

            # Enforce size limits
            final = self.enforce_size_limit(filtered, memory_type)

            results[memory_type] = {
                "original_count": original_count,
                "retained_count": len(final),
                "removed_count": original_count - len(final),
            }

            logger.info(
                "Cleaned up %s memories: %d -> %d (%d removed)",
                memory_type,
                original_count,
                len(final),
                original_count - len(final),
            )

        return results

    def get_memory_stats(self, memories: dict[str, list[T]]) -> dict[str, dict[str, int | float]]:
        """Get statistics for memory collections."""
        stats: dict[str, dict[str, int | float]] = {}
        for memory_type, memory_list in memories.items():
            limit = self.max_memories.get(memory_type, 1000)
            stats[memory_type] = {
                "count": len(memory_list),
                "limit": limit,
                "usage_percent": (len(memory_list) / limit * 100) if limit > 0 else 0,
            }
        return stats
