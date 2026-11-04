"""TDD tests for performance_monitor type fixes (B2.2).

get_current_stats must return a dict that supports subscripting.
"""

from unittest.mock import patch


def test_get_current_stats_returns_subscriptable_dict():
    """get_current_stats must return a dict with nested dicts, not scalars."""
    from src.core.monitoring.performance_monitor import MetricsCollector

    collector = MetricsCollector()
    stats = collector.get_current_stats()

    assert isinstance(stats, dict)
    assert isinstance(stats["current"], dict)
    assert "cpu_percent" in stats["current"]

    # aggregated_5min is either a dict or None
    aggregated = stats.get("aggregated_5min")
    if aggregated is not None:
        assert isinstance(aggregated, dict)
        assert "avg_response_time" in aggregated
