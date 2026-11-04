"""Priority Queue - SLA-aware task prioritization

Features:
- PriorityLevel: CRITICAL, HIGH, NORMAL, LOW, BACKGROUND
- Tenant-to-priority mapping
- Redis SortedSet backing
- Explicit priority overrides

Priority scoring:
score = priority * 1_000_000_000 + timestamp
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import redis


class PriorityLevel(Enum):
    """Priority levels for tasks."""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


class TenantTier(Enum):
    """Tenant tiers for default priority mapping."""

    ENTERPRISE = "enterprise"  # -> HIGH
    STANDARD = "standard"  # -> NORMAL
    FREE = "free"  # -> LOW


@dataclass
class PriorityTask:
    """A task with priority information."""

    task_id: str
    tenant_id: int
    priority: PriorityLevel
    timestamp: float
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type

    @property
    def score(self) -> int:
        """Calculate Redis sorted set score."""
        # Higher priority (lower number) = higher score
        # Earlier timestamp = higher score within same priority
        return self.priority.value * 1_000_000_000 + int(self.timestamp)


class PriorityQueueManager:
    """Manages priority queue with Redis backing."""

    # Default priority by tenant tier
    TIER_PRIORITY = {
        TenantTier.ENTERPRISE: PriorityLevel.HIGH,
        TenantTier.STANDARD: PriorityLevel.NORMAL,
        TenantTier.FREE: PriorityLevel.LOW,
    }

    def __init__(
        self,
        redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Initialize with optional Redis client."""
        self._redis = redis_client
        self._queue_name = "priority_queue"

    def get_priority_for_tier(self, tier: TenantTier) -> PriorityLevel:
        """Get default priority for tenant tier."""
        return self.TIER_PRIORITY.get(tier, PriorityLevel.NORMAL)

    def calculate_score(
        self,
        priority: PriorityLevel,
        timestamp: float | None = None,
    ) -> int:
        """
        Calculate Redis sorted set score.

        Score = priority * 1_000_000_000 + timestamp

        Lower priority value = higher priority (processed first).
        Earlier timestamp = processed first within same priority.
        """
        ts = int(timestamp or time.time())
        return priority.value * 1_000_000_000 + ts

    async def enqueue(
        self,
        task_id: str,
        tenant_id: int,
        priority: PriorityLevel,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> PriorityTask:
        """Add task to priority queue."""
        task = PriorityTask(
            task_id=task_id,
            tenant_id=tenant_id,
            priority=priority,
            timestamp=time.time(),
            data=data,
        )

        if self._redis:
            # Add to Redis sorted set
            await self._redis.zadd(
                self._queue_name,
                {task_id: task.score},
            )

        return task

    async def dequeue(self) -> PriorityTask | None:
        """Get highest priority task (lowest score)."""
        if not self._redis:
            return None

        # Get task with lowest score (highest priority)
        result = await self._redis.zpopmin(self._queue_name, count=1)

        if not result:
            return None

        # Note: In real implementation, would deserialize task data
        task_id, score = result[0]

        # Calculate priority from score
        priority_value = int(score) // 1_000_000_000
        priority = PriorityLevel(priority_value)

        return PriorityTask(
            task_id=task_id.decode() if isinstance(task_id, bytes) else task_id,
            tenant_id=0,  # Would be stored in data
            priority=priority,
            timestamp=score % 1_000_000_000,
            data={},
        )

    async def get_queue_length(self) -> int:
        """Get number of tasks in queue."""
        if not self._redis:
            return 0
        length: int = await self._redis.zcard(self._queue_name)
        return length


# Singleton
_priority_queue_instance: PriorityQueueManager | None = None


def get_priority_queue(redis_client: redis.Redis | None = None) -> PriorityQueueManager:  # type: ignore[type-arg]
    """Get singleton PriorityQueueManager."""
    global _priority_queue_instance
    if _priority_queue_instance is None:
        _priority_queue_instance = PriorityQueueManager(redis_client)
    return _priority_queue_instance
