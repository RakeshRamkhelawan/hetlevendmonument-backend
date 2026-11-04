"""
Comprehensive tests for src/core/monitoring/metrics_collector.py
Coverage target: 100% of metrics collection
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.monitoring.metrics_collector import (
    SystemMetrics,
    collect_system_metrics,
    get_basic_health_check,
)


class TestSystemMetrics:
    """Test SystemMetrics dataclass"""

    def test_system_metrics_creation(self):
        """Test creating SystemMetrics"""
        now = datetime.now(timezone.utc)
        metrics = SystemMetrics(
            timestamp=now,
            cpu_percent=45.5,
            memory_percent=60.2,
            disk_usage_percent=70.8,
            network_connections=50,
            process_count=200,
        )

        assert metrics.timestamp == now
        assert metrics.cpu_percent == 45.5
        assert metrics.memory_percent == 60.2
        assert metrics.disk_usage_percent == 70.8
        assert metrics.network_connections == 50
        assert metrics.process_count == 200


class TestCollectSystemMetrics:
    """Test collect_system_metrics function"""

    @patch("src.core.monitoring.metrics_collector.psutil")
    def test_collect_metrics_success(self, mock_psutil):
        """Test successful metrics collection"""
        # Mock psutil functions
        mock_psutil.cpu_percent.return_value = 25.5
        mock_psutil.virtual_memory.return_value = Mock(percent=50.0)
        mock_psutil.disk_usage.return_value = Mock(percent=65.0)
        mock_psutil.net_connections.return_value = [1, 2, 3, 4, 5]
        mock_psutil.pids.return_value = list(range(150))

        metrics = collect_system_metrics()

        assert isinstance(metrics, SystemMetrics)
        assert metrics.cpu_percent == 25.5
        assert metrics.memory_percent == 50.0
        assert metrics.disk_usage_percent == 65.0
        assert metrics.network_connections == 5
        assert metrics.process_count == 150
        assert isinstance(metrics.timestamp, datetime)

    @patch("src.core.monitoring.metrics_collector.psutil")
    def test_collect_metrics_cpu_interval(self, mock_psutil):
        """Test CPU collection uses interval"""
        mock_psutil.cpu_percent.return_value = 30.0
        mock_psutil.virtual_memory.return_value = Mock(percent=40.0)
        mock_psutil.disk_usage.return_value = Mock(percent=50.0)
        mock_psutil.net_connections.return_value = []
        mock_psutil.pids.return_value = []

        collect_system_metrics()

        # Verify CPU percent called with interval
        mock_psutil.cpu_percent.assert_called_once_with(interval=0.1)

    @patch("src.core.monitoring.metrics_collector.psutil")
    def test_collect_metrics_high_values(self, mock_psutil):
        """Test metrics collection with high values"""
        mock_psutil.cpu_percent.return_value = 95.8
        mock_psutil.virtual_memory.return_value = Mock(percent=98.2)
        mock_psutil.disk_usage.return_value = Mock(percent=99.9)
        mock_psutil.net_connections.return_value = list(range(1000))
        mock_psutil.pids.return_value = list(range(500))

        metrics = collect_system_metrics()

        assert metrics.cpu_percent == 95.8
        assert metrics.memory_percent == 98.2
        assert metrics.disk_usage_percent == 99.9
        assert metrics.network_connections == 1000
        assert metrics.process_count == 500

    @patch("src.core.monitoring.metrics_collector.psutil")
    def test_collect_metrics_low_values(self, mock_psutil):
        """Test metrics collection with low values"""
        mock_psutil.cpu_percent.return_value = 1.5
        mock_psutil.virtual_memory.return_value = Mock(percent=5.0)
        mock_psutil.disk_usage.return_value = Mock(percent=10.0)
        mock_psutil.net_connections.return_value = [1]
        mock_psutil.pids.return_value = [1, 2]

        metrics = collect_system_metrics()

        assert metrics.cpu_percent == 1.5
        assert metrics.memory_percent == 5.0
        assert metrics.disk_usage_percent == 10.0
        assert metrics.network_connections == 1
        assert metrics.process_count == 2

    @patch("src.core.monitoring.metrics_collector.psutil")
    def test_collect_metrics_fallback_on_error(self, mock_psutil):
        """Test fallback metrics when psutil fails"""
        # Make psutil raise an exception
        mock_psutil.cpu_percent.side_effect = Exception("psutil failed")

        metrics = collect_system_metrics()

        # Should return zero values as fallback
        assert isinstance(metrics, SystemMetrics)
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0
        assert metrics.disk_usage_percent == 0.0
        assert metrics.network_connections == 0
        assert metrics.process_count == 0
        assert isinstance(metrics.timestamp, datetime)

    @patch("src.core.monitoring.metrics_collector.psutil")
    def test_collect_metrics_partial_failure(self, mock_psutil):
        """Test partial failure during metrics collection"""
        # First call succeeds, second fails
        mock_psutil.cpu_percent.side_effect = [10.0, Exception("Failed")]
        mock_psutil.virtual_memory.side_effect = Exception("Failed")

        metrics = collect_system_metrics()

        # Should return fallback metrics
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0


class TestGetBasicHealthCheck:
    """Test get_basic_health_check function"""

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_healthy_status(self, mock_collect):
        """Test health check returns healthy status"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=50.0,
            memory_percent=60.0,
            disk_usage_percent=70.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "healthy"
        assert health["cpu_percent"] == 50.0
        assert health["memory_percent"] == 60.0
        assert "timestamp" in health

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_warning_high_cpu(self, mock_collect):
        """Test health check warning status on high CPU"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=85.0,
            memory_percent=70.0,
            disk_usage_percent=50.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "warning"
        assert health["cpu_percent"] == 85.0

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_warning_high_memory(self, mock_collect):
        """Test health check warning status on high memory"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=50.0,
            memory_percent=90.0,
            disk_usage_percent=50.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "warning"
        assert health["memory_percent"] == 90.0

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_warning_both_high(self, mock_collect):
        """Test health check warning when both CPU and memory high"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=85.0,
            memory_percent=90.0,
            disk_usage_percent=50.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "warning"

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_cpu_threshold(self, mock_collect):
        """Test health check at CPU threshold (80%)"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=79.9,
            memory_percent=70.0,
            disk_usage_percent=50.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "healthy"

        # Just above threshold
        mock_metrics.cpu_percent = 80.1
        health = get_basic_health_check()

        assert health["status"] == "warning"

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_memory_threshold(self, mock_collect):
        """Test health check at memory threshold (85%)"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=50.0,
            memory_percent=84.9,
            disk_usage_percent=50.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "healthy"

        # Just above threshold
        mock_metrics.memory_percent = 85.1
        health = get_basic_health_check()

        assert health["status"] == "warning"

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_timestamp_format(self, mock_collect):
        """Test health check timestamp is ISO format"""
        now = datetime.now(timezone.utc)
        mock_metrics = SystemMetrics(
            timestamp=now,
            cpu_percent=50.0,
            memory_percent=60.0,
            disk_usage_percent=70.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["timestamp"] == now.isoformat()

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_low_resources(self, mock_collect):
        """Test health check with very low resource usage"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=5.0,
            memory_percent=10.0,
            disk_usage_percent=20.0,
            network_connections=2,
            process_count=50,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        assert health["status"] == "healthy"
        assert health["cpu_percent"] == 5.0
        assert health["memory_percent"] == 10.0

    @patch("src.core.monitoring.metrics_collector.collect_system_metrics")
    def test_health_check_includes_all_fields(self, mock_collect):
        """Test health check includes all required fields"""
        mock_metrics = SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=50.0,
            memory_percent=60.0,
            disk_usage_percent=70.0,
            network_connections=10,
            process_count=100,
        )
        mock_collect.return_value = mock_metrics

        health = get_basic_health_check()

        required_fields = ["status", "cpu_percent", "memory_percent", "timestamp"]
        for field in required_fields:
            assert field in health
