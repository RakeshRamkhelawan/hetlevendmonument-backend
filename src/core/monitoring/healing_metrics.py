"""
F8: Healing system Prometheus metrics for observability.

Tracks:
- healing_failures_detected_total: Counter of failures detected (by type)
- healing_repairs_executed_total: Counter of repairs executed (by strategy)
- healing_repair_success_rate: Gauge of success rate (rolling window)
- healing_repair_duration_seconds: Histogram of repair execution time
- healing_active_failures: Gauge of currently-tracked failures (real-time)
"""

from prometheus_client import Counter, Gauge, Histogram

# Counters
healing_failures_detected = Counter(
    "healing_failures_detected_total",
    "Total failures detected by healing system",
    ["failure_type"],
)

healing_repairs_executed = Counter(
    "healing_repairs_executed_total",
    "Total repairs executed by healing system",
    ["strategy", "success"],
)

# Gauges
healing_repair_success_rate = Gauge(
    "healing_repair_success_rate",
    "Success rate of repairs (0.0-1.0)",
)

healing_active_failures = Gauge(
    "healing_active_failures",
    "Number of currently-tracked active failures",
)

# Histogram
healing_repair_duration = Histogram(
    "healing_repair_duration_seconds",
    "Duration of repair execution in seconds",
    ["strategy"],
)


def record_failure_detected(failure_type: str) -> None:
    """Record a detected failure."""
    healing_failures_detected.labels(failure_type=failure_type).inc()


def record_repair_executed(strategy: str, success: bool) -> None:
    """Record an executed repair."""
    healing_repairs_executed.labels(strategy=strategy, success="true" if success else "false").inc()


def set_success_rate(rate: float) -> None:
    """Update the moving success rate (0.0-1.0)."""
    healing_repair_success_rate.set(max(0.0, min(1.0, rate)))


def set_active_failures(count: int) -> None:
    """Update the count of active failures."""
    healing_active_failures.set(max(0, count))


def record_repair_duration(strategy: str, duration_seconds: float) -> None:
    """Record repair duration in histogram."""
    healing_repair_duration.labels(strategy=strategy).observe(duration_seconds)
