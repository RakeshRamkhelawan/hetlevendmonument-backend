#!/usr/bin/env python3
"""
Performance Monitor for M-MDP System
Real-time performance tracking and metrics collection
"""

import logging
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from collections.abc import Callable

import psutil

logger = logging.getLogger("PerformanceMonitor")


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    network_sent_mb: float
    network_recv_mb: float
    response_time_ms: float = 0.0
    active_threads: int = 0
    error_count: int = 0


@dataclass
class MetricsAggregation:
    """Aggregated metrics over time period"""

    start_time: datetime
    end_time: datetime
    avg_cpu: float
    avg_memory: float
    avg_response_time: float
    max_response_time: float
    min_response_time: float
    total_requests: int
    error_rate: float
    throughput_rps: float


class MetricsCollector:
    """Collects and aggregates system metrics"""

    def __init__(self, max_history: int = 1000) -> None:
        self.max_history = max_history
        self.metrics_history: deque[PerformanceMetrics] = deque(maxlen=max_history)
        self.response_times: deque[float] = deque(maxlen=max_history)
        self.request_count = 0
        self.error_count = 0
        self.start_time = datetime.now(timezone.utc)
        self._last_disk_io: Any = None  # psutil disk_io_counters type varies by platform
        self._last_network_io: Any = None  # psutil net_io_counters type varies by platform

    def collect_system_metrics(self) -> PerformanceMetrics:
        """Collect current system performance metrics"""
        try:
            # CPU and Memory
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)

            # Disk I/O
            disk_io = psutil.disk_io_counters()
            if self._last_disk_io and disk_io is not None:
                disk_read_mb = (disk_io.read_bytes - self._last_disk_io.read_bytes) / (1024 * 1024)
                disk_write_mb = (disk_io.write_bytes - self._last_disk_io.write_bytes) / (
                    1024 * 1024
                )
            else:
                disk_read_mb = disk_write_mb = 0.0
            self._last_disk_io = disk_io

            # Network I/O
            network_io = psutil.net_io_counters()
            if self._last_network_io:
                network_sent_mb = (network_io.bytes_sent - self._last_network_io.bytes_sent) / (
                    1024 * 1024
                )
                network_recv_mb = (network_io.bytes_recv - self._last_network_io.bytes_recv) / (
                    1024 * 1024
                )
            else:
                network_sent_mb = network_recv_mb = 0.0
            self._last_network_io = network_io

            # Thread count
            active_threads = threading.active_count()

            metrics = PerformanceMetrics(
                timestamp=datetime.now(timezone.utc),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                disk_io_read_mb=disk_read_mb,
                disk_io_write_mb=disk_write_mb,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb,
                active_threads=active_threads,
                error_count=self.error_count,
            )

            self.metrics_history.append(metrics)
            return metrics

        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            return PerformanceMetrics(
                timestamp=datetime.now(timezone.utc),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                disk_io_read_mb=0.0,
                disk_io_write_mb=0.0,
                network_sent_mb=0.0,
                network_recv_mb=0.0,
            )

    def record_response_time(self, response_time_ms: float) -> None:
        """Record API response time"""
        self.response_times.append(response_time_ms)
        self.request_count += 1

    def record_error(self) -> None:
        """Record an error occurrence"""
        self.error_count += 1

    def get_aggregated_metrics(self, minutes: int = 5) -> MetricsAggregation | None:
        """Get aggregated metrics for the last N minutes"""
        if not self.metrics_history:
            return None

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        recent_metrics = [m for m in self.metrics_history if m.timestamp > cutoff_time]

        if not recent_metrics:
            return None

        # Calculate aggregations
        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_percent for m in recent_metrics]

        recent_response_times = [rt for rt in self.response_times]
        if not recent_response_times:
            recent_response_times = [0.0]

        return MetricsAggregation(
            start_time=recent_metrics[0].timestamp,
            end_time=recent_metrics[-1].timestamp,
            avg_cpu=statistics.mean(cpu_values),
            avg_memory=statistics.mean(memory_values),
            avg_response_time=statistics.mean(recent_response_times),
            max_response_time=max(recent_response_times),
            min_response_time=min(recent_response_times),
            total_requests=self.request_count,
            error_rate=(self.error_count / max(self.request_count, 1)) * 100,
            throughput_rps=self.request_count
            / max((datetime.now(timezone.utc) - self.start_time).total_seconds(), 1),
        )

    def get_current_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current performance statistics"""
        latest_metrics = self.collect_system_metrics()
        aggregated = self.get_aggregated_metrics(5)

        return {
            "current": {
                "cpu_percent": latest_metrics.cpu_percent,
                "memory_percent": latest_metrics.memory_percent,
                "memory_used_mb": latest_metrics.memory_used_mb,
                "active_threads": latest_metrics.active_threads,
                "timestamp": latest_metrics.timestamp.isoformat(),
            },
            "aggregated_5min": (
                {
                    "avg_cpu": aggregated.avg_cpu if aggregated else 0,
                    "avg_memory": aggregated.avg_memory if aggregated else 0,
                    "avg_response_time": aggregated.avg_response_time if aggregated else 0,
                    "error_rate": aggregated.error_rate if aggregated else 0,
                    "throughput_rps": aggregated.throughput_rps if aggregated else 0,
                }
                if aggregated
                else None
            ),
            "totals": {
                "total_requests": self.request_count,
                "total_errors": self.error_count,
                "uptime_seconds": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
            },
        }


class PerformanceMonitor:
    """Main performance monitoring system"""

    def __init__(self, collection_interval: int = 30) -> None:
        self.collection_interval = collection_interval
        self.metrics_collector = MetricsCollector()
        self.running = False
        self.monitor_thread: threading.Thread | None = None
        self.callbacks: list[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

    def add_callback(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add callback to be called when metrics are collected"""
        self.callbacks.append(callback)

    def start_monitoring(self) -> None:
        """Start continuous performance monitoring"""
        if self.running:
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"Performance monitoring started (interval: {self.collection_interval}s)")

    def stop_monitoring(self) -> None:
        """Stop performance monitoring"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")

    def _monitoring_loop(self) -> None:
        """Main monitoring loop"""
        while self.running:
            try:
                metrics = self.metrics_collector.collect_system_metrics()

                # Call registered callbacks
                for callback in self.callbacks:
                    try:
                        callback(metrics)
                    except Exception as e:
                        logger.error(f"Monitoring callback failed: {e}")

                time.sleep(self.collection_interval)

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                time.sleep(self.collection_interval)

    def get_health_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get system health status"""
        stats = self.metrics_collector.get_current_stats()
        current = stats["current"]

        # Health thresholds
        cpu_threshold = 80.0
        memory_threshold = 85.0
        response_time_threshold = 1000.0  # 1 second

        health_status = "healthy"
        issues: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if current["cpu_percent"] > cpu_threshold:
            health_status = "warning"
            issues.append(f"High CPU usage: {current['cpu_percent']:.1f}%")

        if current["memory_percent"] > memory_threshold:
            health_status = "critical"
            issues.append(f"High memory usage: {current['memory_percent']:.1f}%")

        aggregated = stats["aggregated_5min"]
        if aggregated and aggregated["avg_response_time"] > response_time_threshold:
            health_status = "warning"
            issues.append(f"Slow response times: {aggregated['avg_response_time']:.1f}ms")

        return {
            "status": health_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "issues": issues,
            "metrics": stats,
            "monitoring_active": self.running,
        }


# Global performance monitor instance
_performance_monitor: PerformanceMonitor | None = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get global performance monitor instance (singleton)"""
    global _performance_monitor

    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()

    return _performance_monitor


def start_performance_monitoring() -> None:
    """Start global performance monitoring"""
    monitor = get_performance_monitor()
    monitor.start_monitoring()


def get_system_health() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current system health status"""
    monitor = get_performance_monitor()
    return monitor.get_health_status()
