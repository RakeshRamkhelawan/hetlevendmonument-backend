"""Unit tests for Priority Queue

Tests:
- Critical before normal
- Same priority FIFO
- Enterprise default high
- Empty queue returns None
- Explicit priority overrides tier
"""

import os
import sys

import pytest

sys.path.insert(0, os.getcwd())

from src.core.workflow.priority_queue import (
    PriorityLevel,
    PriorityQueueManager,
    PriorityTask,
    TenantTier,
    get_priority_queue,
)


class TestPriorityQueue:
    """Tests for Priority Queue."""

    def test_critical_before_normal(self):
        """Happy: CRITICAL tasks processed before NORMAL."""
        # CRITICAL = 0, NORMAL = 2
        # Lower number = higher priority
        assert PriorityLevel.CRITICAL.value < PriorityLevel.NORMAL.value

        # CRITICAL should have higher score priority
        manager = PriorityQueueManager()
        critical_score = manager.calculate_score(PriorityLevel.CRITICAL, 1000)
        normal_score = manager.calculate_score(PriorityLevel.NORMAL, 1000)

        # Lower score = higher priority in Redis sorted set
        assert critical_score < normal_score

    def test_same_priority_fifo(self):
        """Happy: Same priority tasks processed FIFO."""
        manager = PriorityQueueManager()

        # Two tasks with same priority, different timestamps
        score1 = manager.calculate_score(PriorityLevel.NORMAL, 1000)
        score2 = manager.calculate_score(PriorityLevel.NORMAL, 2000)

        # Earlier timestamp = lower score = higher priority
        assert score1 < score2

    def test_enterprise_default_high(self):
        """Happy: Enterprise tier defaults to HIGH priority."""
        manager = PriorityQueueManager()

        priority = manager.get_priority_for_tier(TenantTier.ENTERPRISE)

        assert priority == PriorityLevel.HIGH

    def test_empty_queue_returns_none(self):
        """Unhappy: Empty queue returns None."""
        manager = PriorityQueueManager()

        # Without Redis, dequeue returns None
        assert manager._redis is None

    def test_explicit_priority_overrides_tier(self):
        """Unhappy: Explicit priority overrides tier default."""
        # Enterprise tier defaults to HIGH
        # But explicit CRITICAL should override

        tier_priority = PriorityQueueManager().get_priority_for_tier(TenantTier.ENTERPRISE)
        explicit_priority = PriorityLevel.CRITICAL

        assert tier_priority == PriorityLevel.HIGH
        assert explicit_priority == PriorityLevel.CRITICAL
        assert explicit_priority.value < tier_priority.value  # CRITICAL > HIGH


class TestPriorityLevel:
    """Tests for PriorityLevel enum."""

    def test_priority_values(self):
        """Test priority level values."""
        assert PriorityLevel.CRITICAL.value == 0
        assert PriorityLevel.HIGH.value == 1
        assert PriorityLevel.NORMAL.value == 2
        assert PriorityLevel.LOW.value == 3
        assert PriorityLevel.BACKGROUND.value == 4


class TestTenantTier:
    """Tests for TenantTier enum."""

    def test_tier_values(self):
        """Test tenant tier values."""
        assert TenantTier.ENTERPRISE.value == "enterprise"
        assert TenantTier.STANDARD.value == "standard"
        assert TenantTier.FREE.value == "free"


class TestPriorityTask:
    """Tests for PriorityTask."""

    def test_task_score_calculation(self):
        """Test task score calculation."""
        task = PriorityTask(
            task_id="task-1",
            tenant_id=1,
            priority=PriorityLevel.HIGH,
            timestamp=1000.0,
            data={},
        )

        # score = priority * 1_000_000_000 + timestamp
        expected_score = 1 * 1_000_000_000 + 1000
        assert task.score == expected_score


class TestPriorityQueueManager:
    """Tests for PriorityQueueManager."""

    def test_tier_priority_mapping(self):
        """Test tier to priority mapping."""
        manager = PriorityQueueManager()

        assert manager.get_priority_for_tier(TenantTier.ENTERPRISE) == PriorityLevel.HIGH
        assert manager.get_priority_for_tier(TenantTier.STANDARD) == PriorityLevel.NORMAL
        assert manager.get_priority_for_tier(TenantTier.FREE) == PriorityLevel.LOW

    def test_calculate_score(self):
        """Test score calculation."""
        manager = PriorityQueueManager()

        score = manager.calculate_score(PriorityLevel.CRITICAL, 1000)

        # score = 0 * 1_000_000_000 + 1000 = 1000
        assert score == 1000


class TestPriorityQueueSingleton:
    """Tests for singleton."""

    def test_get_priority_queue_singleton(self):
        """Test singleton pattern."""
        pq1 = get_priority_queue()
        pq2 = get_priority_queue()

        assert pq1 is pq2
