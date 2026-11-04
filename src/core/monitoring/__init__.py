#!/usr/bin/env python3
"""
Core Monitoring Module for M-MDP System
Real-time performance monitoring and analytics
"""

from typing import Any

from .alert_system import AlertLevel, AlertSystem
from .metrics_collector import SystemMetrics, collect_system_metrics
from .performance_monitor import MetricsCollector, PerformanceMonitor
from src.core.observability.metrics import REQUEST_COUNT, REQUEST_LATENCY

__version__ = "3.0.0"
__all__ = [
    "PerformanceMonitor",
    "MetricsCollector",
    "AlertSystem",
    "AlertLevel",
    "SystemMetrics",
    "collect_system_metrics",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
]
