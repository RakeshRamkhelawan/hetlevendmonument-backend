"""
Performance metrics for Learning and Feedback processing.

Provides:
- Latency tracking for database operations
- Counter metrics for rule applications
- Histogram for feedback processing duration
"""

import logging
import time
import types
from collections.abc import Callable
from functools import wraps
from typing import Any

from prometheus_client import Counter, Gauge, Histogram, Info

from src.core.monitoring.prometheus_metrics import (
    learning_adaptation_applied,
    learning_cross_agent_shares,
    learning_observations_total,
    learning_patterns_active,
)

logger = logging.getLogger(__name__)

# Prometheus metrics
LEARNING_INFO = Info("learning_service", "Learning service information")

FEEDBACK_PROCESSING_DURATION = Histogram(
    "feedback_processing_duration_seconds",
    "Time spent processing feedback",
    ["tenant_id", "status"],
)

RULE_APPLICATION_DURATION = Histogram(
    "rule_application_duration_seconds", "Time spent applying adaptation rules", ["tenant_id"]
)

RULE_APPLICATION_COUNTER = Counter(
    "rule_applications_total",
    "Total number of rule applications",
    ["tenant_id", "rule_id", "success"],
)

DB_OPERATION_DURATION = Histogram(
    "learning_db_operation_duration_seconds",
    "Time spent on database operations",
    ["operation", "entity"],
)

ACTIVE_RULES_GAUGE = Gauge(
    "learning_active_rules", "Number of active adaptation rules", ["tenant_id"]
)

INSIGHTS_PROCESSED_COUNTER = Counter(
    "learning_insights_processed_total",
    "Total number of insights processed",
    ["tenant_id", "category"],
)

# =============================================================================
# ADR-026 Digital Twin Production Hardening Metrics
# =============================================================================

TWIN_LLM_PROVIDER_FAILURES = Counter(
    "twin_llm_provider_failures_total",
    "Total LLM provider failures in Twin failover chain",
    ["provider"],
)

TWIN_LLM_PROVIDER_CIRCUIT_OPEN = Counter(
    "twin_llm_provider_circuit_open_total",
    "Total times a provider circuit breaker opened",
    ["provider"],
)

TWIN_LLM_COST_EUR = Counter(
    "twin_llm_cost_eur_total",
    "Total LLM cost in EUR per tenant",
    ["tenant_id"],
)

TWIN_RETENTION_DELETED_ROWS = Counter(
    "twin_retention_deleted_rows_total",
    "Total rows deleted by twin retention cleanup",
    ["table"],
)

TWIN_AGGREGATION_USERS_PROCESSED = Counter(
    "twin_aggregation_users_processed_total",
    "Total users processed by profile aggregation",
    ["tenant_id"],
)

TWIN_HARD_DELETE_PENDING = Gauge(
    "twin_hard_delete_pending_count",
    "Number of users with pending hard delete requests",
)

TWIN_LLM_BUDGET_HARD_EUR = Gauge(
    "twin_llm_budget_hard_eur",
    "Hard budget cap in EUR per tenant for Twin LLM usage",
    ["tenant_id"],
)

# Initialize info
LEARNING_INFO.info({"version": "1.0.0", "persistence": "postgresql"})


def record_learning_observation(tenant_id: int, learning_type: str) -> None:
    """Increment the learning observation counter."""
    learning_observations_total.labels(tenant_id=str(tenant_id), learning_type=learning_type).inc()


def set_learning_patterns_active(tenant_id: int, count: int) -> None:
    """Set the active-pattern gauge for a tenant."""
    learning_patterns_active.labels(tenant_id=str(tenant_id)).set(count)


def record_learning_adaptation_applied(tenant_id: int, success: bool) -> None:
    """Increment the adaptation-applied counter."""
    learning_adaptation_applied.labels(
        tenant_id=str(tenant_id), outcome="success" if success else "failure"
    ).inc()


def record_learning_cross_agent_share(
    tenant_id: int,
    source_agent_type: str,
    target_agent_type: str,
) -> None:
    """Increment the cross-agent-share counter."""
    learning_cross_agent_shares.labels(
        tenant_id=str(tenant_id),
        source_agent_type=source_agent_type or "unknown",
        target_agent_type=target_agent_type or "unknown",
    ).inc()


# ---------------------------------------------------------------------------
# ADR-026 metric helpers
# ---------------------------------------------------------------------------


def record_twin_llm_provider_failure(provider: str) -> None:
    """Record an LLM provider failure in the Twin failover chain."""
    TWIN_LLM_PROVIDER_FAILURES.labels(provider=provider or "unknown").inc()


def record_twin_llm_provider_circuit_open(provider: str) -> None:
    """Record a circuit breaker opening for an LLM provider."""
    TWIN_LLM_PROVIDER_CIRCUIT_OPEN.labels(provider=provider or "unknown").inc()


def record_twin_llm_cost(tenant_id: int, cost_eur: float) -> None:
    """Record LLM cost in EUR for a tenant."""
    if cost_eur > 0:
        TWIN_LLM_COST_EUR.labels(tenant_id=str(tenant_id)).inc(cost_eur)


def record_twin_retention_deleted(table: str, count: int) -> None:
    """Record rows deleted by twin retention cleanup."""
    if count > 0:
        TWIN_RETENTION_DELETED_ROWS.labels(table=table).inc(count)


def record_twin_aggregation_users_processed(tenant_id: int, count: int) -> None:
    """Record users processed by profile aggregation."""
    if count > 0:
        TWIN_AGGREGATION_USERS_PROCESSED.labels(tenant_id=str(tenant_id)).inc(count)


def set_twin_hard_delete_pending(count: int) -> None:
    """Set the number of pending hard delete requests."""
    TWIN_HARD_DELETE_PENDING.set(count)


def set_twin_llm_budget_hard(tenant_id: int, budget_hard: float) -> None:
    """Set the hard budget cap in EUR for a tenant."""
    TWIN_LLM_BUDGET_HARD_EUR.labels(tenant_id=str(tenant_id)).set(budget_hard)


def track_duration(
    metric: Histogram, labels: dict[str, str] | None = None
) -> Callable[
    [Callable[..., Any]], Callable[..., Any]
]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to track function execution duration.

    Usage:
        @track_duration(FEEDBACK_PROCESSING_DURATION, {'status': 'success'})
        async def process_feedback(self, data):
            ...
    """

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                if labels:
                    metric.labels(**labels).observe(time.time() - start)
                else:
                    metric.observe(time.time() - start)
                return result
            except Exception as e:
                if labels:
                    error_labels = {**labels, "status": "error"}
                    metric.labels(**error_labels).observe(time.time() - start)
                else:
                    metric.observe(time.time() - start)
                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()
            try:
                result = func(*args, **kwargs)
                if labels:
                    metric.labels(**labels).observe(time.time() - start)
                else:
                    metric.observe(time.time() - start)
                return result
            except Exception as e:
                if labels:
                    error_labels = {**labels, "status": "error"}
                    metric.labels(**error_labels).observe(time.time() - start)
                else:
                    metric.observe(time.time() - start)
                raise

        return async_wrapper if func.__code__.co_flags & 0x80 else sync_wrapper

    return decorator


class LearningMetricsCollector:
    """
    Collector for learning service metrics.

    Usage:
        metrics = LearningMetricsCollector()
        metrics.record_feedback_processing(tenant_id, duration, success=True)
        metrics.record_rule_application(tenant_id, rule_id, success=True)
    """

    def record_feedback_processing(
        self, tenant_id: str, duration: float, success: bool = True
    ) -> None:
        """Record feedback processing metrics."""
        status = "success" if success else "error"
        FEEDBACK_PROCESSING_DURATION.labels(tenant_id=tenant_id, status=status).observe(duration)

    def record_rule_application(
        self, tenant_id: str, rule_id: str, duration: float, success: bool = True
    ) -> None:
        """Record rule application metrics."""
        RULE_APPLICATION_DURATION.labels(tenant_id=tenant_id).observe(duration)

        RULE_APPLICATION_COUNTER.labels(
            tenant_id=tenant_id, rule_id=rule_id, success="true" if success else "false"
        ).inc()

    def record_db_operation(self, operation: str, entity: str, duration: float) -> None:
        """Record database operation metrics."""
        DB_OPERATION_DURATION.labels(operation=operation, entity=entity).observe(duration)

    def update_active_rules(self, tenant_id: str, count: int) -> None:
        """Update active rules gauge."""
        ACTIVE_RULES_GAUGE.labels(tenant_id=tenant_id).set(count)

    def record_insight_processed(self, tenant_id: str, category: str) -> None:
        """Record insight processing counter."""
        INSIGHTS_PROCESSED_COUNTER.labels(tenant_id=tenant_id, category=category).inc()


class TimedContext:
    """
    Context manager for timing operations.

    Usage:
        with TimedContext(FEEDBACK_PROCESSING_DURATION, {'tenant_id': 'abc'}):
            await process_feedback(data)
    """

    def __init__(self, metric: Histogram, labels: dict[str, str] | None = None) -> None:
        self.metric = metric
        self.labels: dict[str, str] = labels or {}
        self.start_time: float | None = None

    def __enter__(self) -> "TimedContext":
        self.start_time = time.time()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        duration = time.time() - (self.start_time or 0.0)
        if self.labels:
            self.metric.labels(**self.labels).observe(duration)
        else:
            self.metric.observe(duration)


# Convenience decorators for common operations
def track_feedback_processing(
    func: Callable[..., Any],
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """Decorator to track feedback processing duration."""

    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.time()
        tenant_id = kwargs.get("tenant_id", "unknown")
        try:
            result = await func(self, *args, **kwargs)
            FEEDBACK_PROCESSING_DURATION.labels(tenant_id=tenant_id, status="success").observe(
                time.time() - start
            )
            return result
        except Exception as e:
            FEEDBACK_PROCESSING_DURATION.labels(tenant_id=tenant_id, status="error").observe(
                time.time() - start
            )
            raise

    return wrapper


def track_rule_application(
    func: Callable[..., Any],
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """Decorator to track rule application duration."""

    @wraps(func)
    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.time()
        tenant_id = kwargs.get("tenant_id", "unknown")
        try:
            result = await func(self, *args, **kwargs)
            RULE_APPLICATION_DURATION.labels(tenant_id=tenant_id).observe(time.time() - start)
            return result
        except Exception as e:
            RULE_APPLICATION_DURATION.labels(tenant_id=tenant_id).observe(time.time() - start)
            raise

    return wrapper
