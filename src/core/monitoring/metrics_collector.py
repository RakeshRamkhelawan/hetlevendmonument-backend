#!/usr/bin/env python3
"""
System Metrics Collector for M-MDP
Lightweight metrics collection utilities
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

try:
    import psutil
except ImportError:
    psutil: Any = None  # type: ignore[no-redef]


@dataclass
class SystemMetrics:
    """System performance metrics snapshot"""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    network_connections: int
    process_count: int


def collect_system_metrics() -> SystemMetrics:
    """Collect current system metrics"""
    try:
        if psutil is None:
            raise ImportError("psutil not installed")
        return SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=psutil.virtual_memory().percent,
            disk_usage_percent=psutil.disk_usage("/").percent,
            network_connections=len(psutil.net_connections()),
            process_count=len(psutil.pids()),
        )
    except Exception:
        # Fallback metrics if psutil fails
        return SystemMetrics(
            timestamp=datetime.now(timezone.utc),
            cpu_percent=0.0,
            memory_percent=0.0,
            disk_usage_percent=0.0,
            network_connections=0,
            process_count=0,
        )


def get_basic_health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get basic system health information"""
    metrics = collect_system_metrics()

    return {
        "status": (
            "healthy" if metrics.cpu_percent < 80 and metrics.memory_percent < 85 else "warning"
        ),
        "cpu_percent": metrics.cpu_percent,
        "memory_percent": metrics.memory_percent,
        "timestamp": metrics.timestamp.isoformat(),
    }
