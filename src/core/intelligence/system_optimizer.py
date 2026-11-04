"""
System Optimizer Module

Provides system-wide optimization capabilities for the SanskritiSetu platform.
This module handles performance optimization, resource allocation, and adaptive
system tuning based on usage patterns and workload characteristics.

Author: SanskritiSetu Team
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class OptimizationConfig:
    """Configuration for system optimization."""

    # Performance tuning
    max_concurrent_operations: int = 100
    cache_ttl_seconds: int = 300
    batch_size: int = 50

    # Resource allocation
    memory_limit_mb: int = 1024
    cpu_threshold_percent: float = 80.0

    # Adaptive settings
    enable_auto_scaling: bool = True
    scaling_cooldown_seconds: int = 60

    # Monitoring
    metrics_collection_interval: int = 30
    health_check_interval: int = 10


@dataclass
class OptimizationMetrics:
    """Metrics collected during optimization."""

    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    cache_hit_rate: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    active_connections: int = 0


class SystemOptimizer:
    """
    Main system optimizer class.

    Provides methods for:
    - Performance optimization
    - Resource monitoring
    - Adaptive scaling
    - Cache management
    - Workload balancing
    """

    _instance: Optional["SystemOptimizer"] = None

    def __init__(self, config: OptimizationConfig | None = None) -> None:
        """Initialize the system optimizer."""
        self.config = config or OptimizationConfig()
        self.metrics = OptimizationMetrics()
        self._initialized = False
        logger.info("SystemOptimizer initialized with config: %s", self.config)

    @classmethod
    def get_instance(cls, config: OptimizationConfig | None = None) -> "SystemOptimizer":
        """Get singleton instance of SystemOptimizer."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance (for testing)."""
        cls._instance = None

    async def initialize(self) -> None:
        """Initialize the optimizer and start background tasks."""
        if self._initialized:
            logger.warning("SystemOptimizer already initialized")
            return

        logger.info("Initializing SystemOptimizer...")
        self._initialized = True
        logger.info("SystemOptimizer initialization complete")

    async def shutdown(self) -> None:
        """Shutdown the optimizer and cleanup resources."""
        logger.info("Shutting down SystemOptimizer...")
        self._initialized = False
        logger.info("SystemOptimizer shutdown complete")

    def get_metrics(self) -> OptimizationMetrics:
        """Get current optimization metrics."""
        return self.metrics

    def update_metrics(self, **kwargs: Any) -> None:
        """Update optimization metrics."""
        for key, value in kwargs.items():
            if hasattr(self.metrics, key):
                setattr(self.metrics, key, value)

    async def optimize_performance(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Run performance optimization.

        Returns optimization results and recommendations.
        """
        logger.info("Running performance optimization...")

        results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "status": "completed",
            "optimizations_applied": [],
            "recommendations": [],
            "metrics": {
                "cache_hit_rate": self.metrics.cache_hit_rate,
                "average_latency_ms": self.metrics.average_latency_ms,
            },
        }

        # Check cache efficiency
        if self.metrics.cache_hit_rate < 0.5:
            results["recommendations"].append("Consider increasing cache TTL or cache size")

        # Check latency
        if self.metrics.average_latency_ms > 500:
            results["recommendations"].append("High latency detected. Consider query optimization.")

        return results

    async def optimize_resources(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Run resource optimization.

        Returns resource allocation recommendations.
        """
        logger.info("Running resource optimization...")

        results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "status": "completed",
            "current_allocation": {
                "memory_mb": self.metrics.memory_usage_mb,
                "cpu_percent": self.metrics.cpu_usage_percent,
            },
            "recommendations": [],
        }

        # Check memory usage
        if self.metrics.memory_usage_mb > self.config.memory_limit_mb * 0.8:
            results["recommendations"].append(
                "Memory usage approaching limit. Consider scaling up."
            )

        # Check CPU usage
        if self.metrics.cpu_usage_percent > self.config.cpu_threshold_percent:
            results["recommendations"].append("High CPU usage. Consider load balancing.")

        return results

    async def auto_scale(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Perform auto-scaling if enabled.

        Returns scaling decisions made.
        """
        if not self.config.enable_auto_scaling:
            return {"status": "disabled", "message": "Auto-scaling is disabled"}

        logger.info("Running auto-scaling check...")

        decisions: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "status": "completed",
            "actions_taken": [],
        }

        # Scale based on metrics
        if self.metrics.cpu_usage_percent > self.config.cpu_threshold_percent:
            decisions["actions_taken"].append(
                {
                    "action": "scale_out",
                    "reason": "CPU threshold exceeded",
                    "threshold": self.config.cpu_threshold_percent,
                    "current": self.metrics.cpu_usage_percent,
                }
            )

        return decisions

    def get_health_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get system health status."""
        healthy = (
            self.metrics.cpu_usage_percent < self.config.cpu_threshold_percent
            and self.metrics.memory_usage_mb < self.config.memory_limit_mb
        )

        return {
            "healthy": healthy,
            "initialized": self._initialized,
            "metrics": {
                "cpu_usage_percent": self.metrics.cpu_usage_percent,
                "memory_usage_mb": self.metrics.memory_usage_mb,
                "cache_hit_rate": self.metrics.cache_hit_rate,
                "active_connections": self.metrics.active_connections,
            },
        }


# Module-level singleton accessor
_optimizer: SystemOptimizer | None = None


def get_system_optimizer(
    config: OptimizationConfig | None = None,
) -> SystemOptimizer:
    """
    Get the system optimizer instance.

    This is the main entry point for accessing the system optimizer.
    Creates a singleton instance on first call.

    Args:
        config: Optional configuration for the optimizer.

    Returns:
        The SystemOptimizer singleton instance.
    """
    global _optimizer

    if _optimizer is None:
        _optimizer = SystemOptimizer(config)

    return _optimizer


def reset_optimizer() -> None:
    """Reset the optimizer singleton (for testing)."""
    global _optimizer
    _optimizer = None
    SystemOptimizer.reset_instance()


__all__ = [
    "SystemOptimizer",
    "OptimizationConfig",
    "OptimizationMetrics",
    "get_system_optimizer",
    "reset_optimizer",
]
