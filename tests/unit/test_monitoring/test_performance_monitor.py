"""Unit tests for performance_monitor module."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.monitoring.performance_monitor import (
    MetricsAggregation,
    MetricsCollector,
    PerformanceMetrics,
    PerformanceMonitor,
)


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_get_current_stats_returns_dict(self):
        """get_current_stats must return a dictionary with expected keys."""
        collector = MetricsCollector()
        stats = collector.get_current_stats()

        assert isinstance(stats, dict)
        assert "current" in stats
        assert "aggregated_5min" in stats
        assert "totals" in stats

    def test_get_current_stats_current_has_cpu_and_memory(self):
        """The 'current' key must contain cpu_percent and memory_percent."""
        collector = MetricsCollector()
        stats = collector.get_current_stats()
        current = stats["current"]

        assert "cpu_percent" in current
        assert "memory_percent" in current
        assert isinstance(current["cpu_percent"], (int, float))
        assert isinstance(current["memory_percent"], (int, float))

    def test_get_aggregated_metrics_returns_none_when_empty(self):
        """get_aggregated_metrics must return None when history is empty."""
        collector = MetricsCollector()
        assert collector.get_aggregated_metrics(5) is None

    def test_get_current_stats_aggregated_is_dict_after_collection(self):
        """aggregated_5min must be a dict after real metric collection."""
        collector = MetricsCollector()
        fake_psutil = MagicMock()
        fake_psutil.cpu_percent.return_value = 10.0
        fake_mem = MagicMock()
        fake_mem.percent = 50.0
        fake_mem.used = 1024 * 1024 * 100
        fake_psutil.virtual_memory.return_value = fake_mem
        fake_psutil.disk_io_counters.return_value = None
        fake_psutil.net_io_counters.return_value = None

        with patch("src.core.monitoring.performance_monitor.psutil", fake_psutil):
            stats = collector.get_current_stats()

        agg = stats["aggregated_5min"]
        assert isinstance(agg, dict)
        assert "avg_cpu" in agg
        assert "avg_memory" in agg


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor."""

    def test_get_health_status_returns_healthy_when_idle(self):
        """With zero CPU/memory, health status must be healthy."""
        monitor = PerformanceMonitor()
        with patch.object(
            monitor.metrics_collector,
            "get_current_stats",
            return_value={
                "current": {
                    "cpu_percent": 0.0,
                    "memory_percent": 0.0,
                },
                "aggregated_5min": None,
                "totals": {},
            },
        ):
            health = monitor.get_health_status()

        assert health["status"] == "healthy"
        assert health["issues"] == []
        assert health["monitoring_active"] is False

    def test_get_health_status_warns_on_high_cpu(self):
        """CPU above threshold must set warning status."""
        monitor = PerformanceMonitor()
        with patch.object(
            monitor.metrics_collector,
            "get_current_stats",
            return_value={
                "current": {
                    "cpu_percent": 95.0,
                    "memory_percent": 0.0,
                },
                "aggregated_5min": None,
                "totals": {},
            },
        ):
            health = monitor.get_health_status()

        assert health["status"] == "warning"
        assert any("CPU" in issue for issue in health["issues"])

    def test_get_health_status_critical_on_high_memory(self):
        """Memory above threshold must set critical status."""
        monitor = PerformanceMonitor()
        with patch.object(
            monitor.metrics_collector,
            "get_current_stats",
            return_value={
                "current": {
                    "cpu_percent": 0.0,
                    "memory_percent": 95.0,
                },
                "aggregated_5min": None,
                "totals": {},
            },
        ):
            health = monitor.get_health_status()

        assert health["status"] == "critical"
        assert any("memory" in issue for issue in health["issues"])

    def test_get_health_status_warns_on_slow_response_time(self):
        """Slow avg response time must set warning status."""
        monitor = PerformanceMonitor()
        with patch.object(
            monitor.metrics_collector,
            "get_current_stats",
            return_value={
                "current": {
                    "cpu_percent": 0.0,
                    "memory_percent": 0.0,
                },
                "aggregated_5min": {
                    "avg_response_time": 5000.0,
                },
                "totals": {},
            },
        ):
            health = monitor.get_health_status()

        assert health["status"] == "warning"
        assert any("response" in issue for issue in health["issues"])
