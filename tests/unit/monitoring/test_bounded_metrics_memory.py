"""Tests for bounded memory structures in metrics and optimizer singletons."""

from __future__ import annotations

from collections import deque
import pytest

from src.domains.memory.observability import _NoOpHistogram
from src.core.optimization.performance_optimizer import (
    PerformanceOptimizer,
    OptimizationResult,
    OptimizationType,
    OptimizationStrategy,
    OptimizationStatus,
)


def test_noop_histogram_observations_is_bounded_deque() -> None:
    """_NoOpHistogram observations must be a bounded deque to prevent memory leaks."""
    histogram = _NoOpHistogram()
    assert isinstance(histogram.observations, deque)
    assert histogram.observations.maxlen == 1000

    # Observe 1500 items
    for i in range(1500):
        histogram.observe(float(i))

    assert len(histogram.observations) == 1000
    # Oldest items should have been evicted
    assert histogram.observations[0] == 500.0
    assert histogram.observations[-1] == 1499.0


def test_performance_optimizer_history_is_bounded_deque() -> None:
    """PerformanceOptimizer.optimization_history must be bounded to prevent singleton memory leaks."""
    optimizer = PerformanceOptimizer()
    assert isinstance(optimizer.optimization_history, deque)
    assert optimizer.optimization_history.maxlen == 1000

    # Add 1200 items to history
    for i in range(1200):
        result = OptimizationResult(
            optimization_id=f"opt_{i}",
            optimization_type=OptimizationType.CPU_OPTIMIZATION,
            strategy=OptimizationStrategy.BALANCED,
            status=OptimizationStatus.COMPLETED,
            performance_gain=0.1,
            resource_impact={},
            applied_changes=[],
            recommendations=[],
            execution_time=0.5,
            confidence_score=0.8,
            before_metrics={},
            after_metrics={},
        )
        optimizer.optimization_history.append(result)

    assert len(optimizer.optimization_history) == 1000
    assert optimizer.optimization_history[0].optimization_id == "opt_200"
    assert optimizer.optimization_history[-1].optimization_id == "opt_1199"
