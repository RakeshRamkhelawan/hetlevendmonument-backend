"""
Prometheus Metrics for Autonomous Workflow Training System
Production-grade metrics collection with minimal performance impact

Track 1 of 4: Prometheus Metrics Integration
Part of Production Hardening initiative
"""

import logging
import time
from functools import wraps
from typing import Self, cast, Any
from collections.abc import Callable, Awaitable

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "Info",
    "generate_latest",
    "CollectorRegistry",
]

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================================
# SAFE METRICS REGISTRATION (Fix for pytest collection errors)
# ============================================================================

# Cache for created metrics to prevent duplicates across test reruns
_METRICS_CACHE: dict[str, object] = {}


def _find_metric_in_registry(name: str) -> object | None:
    """Find an existing metric in the registry by name."""
    collector_to_names: dict[object, set[str]] = getattr(REGISTRY, "_collector_to_names", {})
    for collector in list(collector_to_names.keys()):
        # Check various possible name attributes
        metric_names = collector_to_names.get(collector, set())
        if name in metric_names:
            return collector
        # Also check the _name attribute
        collector_name: str | None = getattr(collector, "_name", None)
        if collector_name == name:
            return collector
    return None


def get_or_create_histogram(name: str, description: str, **kwargs: object) -> Histogram:
    """Safely get or create a Histogram metric (prevents duplicates in test environments)"""
    if name in _METRICS_CACHE:
        return cast(Histogram, _METRICS_CACHE[name])

    # Try to find existing metric first
    existing_metric = _find_metric_in_registry(name)
    if existing_metric:
        _METRICS_CACHE[name] = existing_metric
        return cast(Histogram, existing_metric)

    try:
        metric = Histogram(name, description, **kwargs)  # type: ignore[arg-type]  # prometheus_client stubs gap
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError as e:
        # Last resort: try to find it again
        if "Duplicated timeseries" in str(e):
            existing_metric = _find_metric_in_registry(name)
            if existing_metric:
                _METRICS_CACHE[name] = existing_metric
                return cast(Histogram, existing_metric)
        logger.warning(f"Failed to create histogram {name}: {e}")
        raise


def get_or_create_counter(
    name: str, description: str, labelnames: list[str] | None = None
) -> Counter:
    """Safely get or create a Counter metric (prevents duplicates in test environments)"""
    if name in _METRICS_CACHE:
        return cast(Counter, _METRICS_CACHE[name])

    # Try to find existing metric first
    existing_metric = _find_metric_in_registry(name)
    if existing_metric:
        _METRICS_CACHE[name] = existing_metric
        return cast(Counter, existing_metric)

    try:
        metric = Counter(name, description, labelnames or [])
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError as e:
        # Last resort: try to find it again
        if "Duplicated timeseries" in str(e):
            existing_metric = _find_metric_in_registry(name)
            if existing_metric:
                _METRICS_CACHE[name] = existing_metric
                logger.debug(f"Reusing existing counter metric: {name}")
                return cast(Counter, existing_metric)
        logger.error(f"Failed to create counter {name}: {e}")
        # In test environments, create a dummy metric to avoid breaking tests
        if "pytest" in str(e) or "test" in name.lower():
            # Create a simple wrapper that does nothing
            class DummyCounter:
                def labels(self, *args: object, **kwargs: object) -> Self:
                    return self

                def inc(self, *args: object, **kwargs: object) -> None:
                    logger.debug("Dummy counter incremented for %s", name)

            dummy = DummyCounter()
            _METRICS_CACHE[name] = dummy
            return cast(Counter, dummy)
        raise


def get_or_create_gauge(name: str, description: str, labelnames: list[str] | None = None) -> Gauge:
    """Safely get or create a Gauge metric (prevents duplicates in test environments)"""
    if name in _METRICS_CACHE:
        return cast(Gauge, _METRICS_CACHE[name])

    # Try to find existing metric first
    existing_metric = _find_metric_in_registry(name)
    if existing_metric:
        _METRICS_CACHE[name] = existing_metric
        return cast(Gauge, existing_metric)

    try:
        metric = Gauge(name, description, labelnames or [])
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError as e:
        # Last resort: try to find it again
        if "Duplicated timeseries" in str(e):
            existing_metric = _find_metric_in_registry(name)
            if existing_metric:
                _METRICS_CACHE[name] = existing_metric
                return cast(Gauge, existing_metric)
        logger.warning(f"Failed to create gauge {name}: {e}")
        raise


def get_or_create_info(name: str, description: str) -> Info:
    """Safely get or create an Info metric (prevents duplicates in test environments)"""
    if name in _METRICS_CACHE:
        return cast(Info, _METRICS_CACHE[name])

    # Try to find existing metric first
    existing_metric = _find_metric_in_registry(name)
    if existing_metric:
        _METRICS_CACHE[name] = existing_metric
        return cast(Info, existing_metric)

    try:
        metric = Info(name, description)
        _METRICS_CACHE[name] = metric
        return metric
    except ValueError as e:
        # Last resort: try to find it again
        if "Duplicated timeseries" in str(e):
            existing_metric = _find_metric_in_registry(name)
            if existing_metric:
                _METRICS_CACHE[name] = existing_metric
                return cast(Info, existing_metric)
        logger.warning(f"Failed to create info {name}: {e}")
        raise


# ============================================================================
# TRAINING METRICS
# ============================================================================

training_duration_seconds: Histogram = get_or_create_histogram(
    "training_duration_seconds",
    "Duration of training sessions in seconds",
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],  # 1s to 1hr
)

training_success_total: Counter = get_or_create_counter(
    "training_success_total",
    "Total number of successful training sessions",
    ["training_type"],  # e.g., 'scheduled', 'manual', 'triggered'
)

training_failure_total: Counter = get_or_create_counter(
    "training_failure_total",
    "Total number of failed training sessions",
    ["training_type", "error_type"],
)

training_skipped_total: Counter = get_or_create_counter(
    "training_skipped_total",
    "Total number of skipped training sessions",
    ["reason"],  # e.g., 'insufficient_data', 'already_running'
)

training_average_loss: Gauge = get_or_create_gauge(
    "training_average_loss", "Average loss from last training session"
)

training_final_loss: Gauge = get_or_create_gauge(
    "training_final_loss", "Final loss from last training session"
)

training_sessions_total: Counter = get_or_create_counter(
    "training_sessions_total", "Total cumulative training sessions since startup"
)


# ============================================================================
# EXPERIENCE METRICS
# ============================================================================

experiences_processed_total: Counter = get_or_create_counter(
    "experiences_processed_total",
    "Total number of learning experiences processed during training",
)

experiences_fetched_total: Counter = get_or_create_counter(
    "experiences_fetched_total",
    "Total number of experiences fetched from database",
    ["query_type"],  # e.g., 'training', 'validation', 'status_check'
)

experiences_available_gauge: Gauge = get_or_create_gauge(
    "experiences_available_gauge",
    "Current number of available experiences in database",
    ["time_window"],  # e.g., '7_days', '30_days'
)

experiences_transformed_total: Counter = get_or_create_counter(
    "experiences_transformed_total",
    "Total number of experiences transformed for training",
)

experiences_transform_duration_seconds: Histogram = get_or_create_histogram(
    "experiences_transform_duration_seconds",
    "Time taken to transform experiences",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],  # 1ms to 1s
)


# ============================================================================
# LEARNING GOVERNANCE METRICS
# ============================================================================

learning_observations_total: Counter = get_or_create_counter(
    "learning_observations_total",
    "Total number of learning observations recorded",
    ["tenant_id", "learning_type"],
)

learning_patterns_active: Gauge = get_or_create_gauge(
    "learning_patterns_active",
    "Number of active learning patterns available",
    ["tenant_id"],
)

learning_adaptation_applied: Counter = get_or_create_counter(
    "learning_adaptation_applied",
    "Total number of learning adaptations applied",
    ["tenant_id", "outcome"],
)

learning_cross_agent_shares: Counter = get_or_create_counter(
    "learning_cross_agent_shares",
    "Total number of cross-agent learning shares",
    ["tenant_id", "source_agent_type", "target_agent_type"],
)


# ============================================================================
# MLFLOW INTEGRATION METRICS
# ============================================================================

mlflow_runs_created_total: Counter = get_or_create_counter(
    "mlflow_runs_created_total", "Total number of MLflow runs created"
)

mlflow_runs_failed_total: Counter = get_or_create_counter(
    "mlflow_runs_failed_total", "Total number of failed MLflow run creations"
)

mlflow_tracking_errors_total: Counter = get_or_create_counter(
    "mlflow_tracking_errors_total",
    "Total number of MLflow tracking errors",
    ["error_type"],  # e.g., 'connection', 'authentication', 'logging'
)

mlflow_params_logged_total: Counter = get_or_create_counter(
    "mlflow_params_logged_total", "Total number of parameters logged to MLflow"
)

mlflow_metrics_logged_total: Counter = get_or_create_counter(
    "mlflow_metrics_logged_total", "Total number of metrics logged to MLflow"
)

mlflow_models_logged_total: Counter = get_or_create_counter(
    "mlflow_models_logged_total", "Total number of models logged to MLflow"
)

mlflow_connection_status: Gauge = get_or_create_gauge(
    "mlflow_connection_status", "MLflow connection status (1=connected, 0=disconnected)"
)


# ============================================================================
# PIPELINE METRICS
# ============================================================================

pipeline_inference_duration_seconds: Histogram = get_or_create_histogram(
    "pipeline_inference_duration_seconds",
    "Duration of pipeline inference operations",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

pipeline_inference_total: Counter = get_or_create_counter(
    "pipeline_inference_total",
    "Total number of pipeline inferences",
    ["status"],  # 'success' or 'failure'
)

model_update_total: Counter = get_or_create_counter(
    "model_update_total", "Total number of model updates/retrains"
)

model_version_info: Info = get_or_create_info(
    "model_version_info", "Information about current model version"
)

pipeline_batch_size: Gauge = get_or_create_gauge(
    "pipeline_batch_size", "Current batch size used in pipeline"
)

pipeline_learning_rate: Gauge = get_or_create_gauge(
    "pipeline_learning_rate", "Current learning rate used in pipeline"
)


# ============================================================================
# SYSTEM HEALTH METRICS
# ============================================================================

training_service_health: Gauge = get_or_create_gauge(
    "training_service_health", "Training service health status (1=healthy, 0=unhealthy)"
)

training_service_ready: Gauge = get_or_create_gauge(
    "training_service_ready", "Training service readiness (1=ready, 0=not ready)"
)

last_training_timestamp: Gauge = get_or_create_gauge(
    "last_training_timestamp", "Unix timestamp of last training session"
)


# ============================================================================
# DECORATOR UTILITIES
# ============================================================================


def track_training_duration(
    training_type: str = "default",
) -> Callable[
    [Callable[..., Awaitable[object]]], Callable[..., Awaitable[object]]
]:
    """
    Decorator to track training duration and success/failure.

    Usage:
        @track_training_duration(training_type='scheduled')
        async def train(...):
            ...
    """

    def decorator(
        func: Callable[..., Awaitable[object]],
    ) -> Callable[..., Awaitable[object]]:
        @wraps(func)
        async def wrapper(
            *args: object, **kwargs: object
        ) -> Any:  # TODO(TYPE): replace Any with concrete type
            start_time: float = time.time()
            try:
                result = await func(*args, **kwargs)
                duration: float = time.time() - start_time

                # Track duration
                training_duration_seconds.observe(duration)

                # Track success/failure based on result
                if isinstance(result, dict):
                    status = result.get("status", "unknown")
                    if status == "success":
                        training_success_total.labels(training_type=training_type).inc()
                        training_sessions_total.inc()

                        # Update loss metrics if available
                        if "metrics" in result:
                            metrics = result["metrics"]
                            if "average_loss" in metrics:
                                training_average_loss.set(metrics["average_loss"])
                            if "final_loss" in metrics:
                                training_final_loss.set(metrics["final_loss"])

                    elif status == "skipped":
                        reason = result.get("reason", "unknown")
                        training_skipped_total.labels(reason=reason).inc()

                    elif status == "failed":
                        error_type = result.get("error_type", "unknown")
                        training_failure_total.labels(
                            training_type=training_type, error_type=error_type
                        ).inc()

                return result

            except Exception as e:
                duration = time.time() - start_time
                training_duration_seconds.observe(duration)
                training_failure_total.labels(
                    training_type=training_type, error_type=type(e).__name__
                ).inc()
                raise

        return wrapper

    return decorator


def track_inference_duration() -> Callable[
    [Callable[..., Awaitable[object]]], Callable[..., Awaitable[object]]
]:
    """
    Decorator to track pipeline inference duration.

    Usage:
        @track_inference_duration()
        async def inference(...):
            ...
    """

    def decorator(
        func: Callable[..., Awaitable[object]],
    ) -> Callable[..., Awaitable[object]]:
        @wraps(func)
        async def wrapper(
            *args: object, **kwargs: object
        ) -> Any:  # TODO(TYPE): replace Any with concrete type
            start_time: float = time.time()
            try:
                result = await func(*args, **kwargs)
                duration: float = time.time() - start_time
                pipeline_inference_duration_seconds.observe(duration)
                pipeline_inference_total.labels(status="success").inc()
                return result
            except Exception:
                duration = time.time() - start_time
                pipeline_inference_duration_seconds.observe(duration)
                pipeline_inference_total.labels(status="failure").inc()
                raise

        return wrapper

    return decorator


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def record_experiences_fetched(count: int, query_type: str = "training") -> None:
    """Record number of experiences fetched from database."""
    experiences_fetched_total.labels(query_type=query_type).inc(count)


def record_experiences_processed(count: int) -> None:
    """Record number of experiences processed during training."""
    experiences_processed_total.inc(count)


def record_experiences_transformed(count: int, duration_seconds: float) -> None:
    """Record experience transformation metrics."""
    experiences_transformed_total.inc(count)
    experiences_transform_duration_seconds.observe(duration_seconds)


def update_experiences_available(count: int, time_window: str = "7_days") -> None:
    """Update gauge with current available experiences."""
    experiences_available_gauge.labels(time_window=time_window).set(count)


def record_mlflow_run_created() -> None:
    """Record successful MLflow run creation."""
    mlflow_runs_created_total.inc()


def record_mlflow_run_failed() -> None:
    """Record failed MLflow run creation."""
    mlflow_runs_failed_total.inc()


def record_mlflow_error(error_type: str) -> None:
    """Record MLflow tracking error."""
    mlflow_tracking_errors_total.labels(error_type=error_type).inc()


def record_mlflow_params_logged(count: int = 1) -> None:
    """Record parameters logged to MLflow."""
    mlflow_params_logged_total.inc(count)


def record_mlflow_metrics_logged(count: int = 1) -> None:
    """Record metrics logged to MLflow."""
    mlflow_metrics_logged_total.inc(count)


def record_mlflow_model_logged() -> None:
    """Record model logged to MLflow."""
    mlflow_models_logged_total.inc()


def set_mlflow_connection_status(connected: bool) -> None:
    """Set MLflow connection status."""
    mlflow_connection_status.set(1 if connected else 0)


def record_model_update() -> None:
    """Record model update/retrain."""
    model_update_total.inc()


def set_model_version(version: str, architecture: str, parameters: int) -> None:
    """Set model version information."""
    model_version_info.info(
        {
            "version": version,
            "architecture": architecture,
            "parameters": str(parameters),
        }
    )


def update_pipeline_config(batch_size: int, learning_rate: float) -> None:
    """Update pipeline configuration metrics."""
    pipeline_batch_size.set(batch_size)
    pipeline_learning_rate.set(learning_rate)


def set_training_service_health(healthy: bool) -> None:
    """Set training service health status."""
    training_service_health.set(1 if healthy else 0)


def set_training_service_ready(ready: bool) -> None:
    """Set training service readiness status."""
    training_service_ready.set(1 if ready else 0)


def set_last_training_timestamp(timestamp: float) -> None:
    """Set timestamp of last training session."""
    last_training_timestamp.set(timestamp)


# ============================================================================
# SLA & ERROR RATE METRICS (Task 5.3.3)
# ============================================================================

# HTTP request metrics for SLA monitoring
# NOTE: Import from observability.metrics to avoid duplication
from src.core.observability.metrics import HTTP_ERRORS_TOTAL as http_errors_total
from src.core.observability.metrics import REQUEST_COUNT as http_requests_total
from src.core.observability.metrics import REQUEST_LATENCY as http_request_duration_seconds

# Error rate tracking
error_rate_gauge: Gauge = get_or_create_gauge(
    "error_rate_percent",
    "Current error rate percentage (5xx errors / total requests * 100)",
    ["window"],  # e.g., '1m', '5m', '15m'
)

# Uptime tracking
uptime_seconds: Gauge = get_or_create_gauge("uptime_seconds", "Application uptime in seconds")

sla_target_uptime_percent: Gauge = get_or_create_gauge(
    "sla_target_uptime_percent", "SLA target uptime percentage (e.g., 99.5)"
)

current_uptime_percent: Gauge = get_or_create_gauge(
    "current_uptime_percent", "Current calculated uptime percentage"
)

# Health check metrics
health_check_total: Counter = get_or_create_counter(
    "health_check_total",
    "Total health checks performed",
    ["check_type", "status"],  # check_type: 'live', 'ready', 'full'
)

health_check_duration_seconds: Histogram = get_or_create_histogram(
    "health_check_duration_seconds",
    "Duration of health checks",
    labelnames=["check_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

component_health_status: Gauge = get_or_create_gauge(
    "component_health_status",
    "Health status of individual components (1=healthy, 0=unhealthy)",
    ["component"],  # e.g., 'database', 'redis', 'llm_api', 'monitoring'
)

# Latency percentiles (for SLA monitoring)
request_latency_p50: Gauge = get_or_create_gauge(
    "request_latency_p50_seconds", "P50 (median) request latency in seconds"
)

request_latency_p95: Gauge = get_or_create_gauge(
    "request_latency_p95_seconds", "P95 request latency in seconds"
)

request_latency_p99: Gauge = get_or_create_gauge(
    "request_latency_p99_seconds", "P99 request latency in seconds"
)

# Alert tracking
alerts_firing: Gauge = get_or_create_gauge(
    "alerts_firing",
    "Number of currently firing alerts",
    ["severity"],  # 'critical', 'warning', 'info'
)

alerts_total: Counter = get_or_create_counter(
    "alerts_total", "Total alerts triggered", ["severity", "alert_name"]
)


class SLAMonitor:
    """
    SLA Monitoring class to track error rates and uptime
    """

    def __init__(self) -> None:
        self._startup_time: float = time.time()
        self._request_count = 0
        self._error_count = 0
        self._downtime_seconds = 0.0
        self._last_check_time: float = time.time()
        self._sla_target = 99.5  # Default SLA target

        # Set initial SLA target
        sla_target_uptime_percent.set(self._sla_target)

    def record_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        tenant_id: str = "system",
    ) -> None:
        """Record an HTTP request for SLA metrics"""
        self._request_count += 1

        # Record to Prometheus
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
            tenant_id=tenant_id,  # Added tenant_id to match observability.metrics schema
        ).inc()

        http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
            tenant_id=tenant_id,  # Added tenant_id to match observability.metrics schema
        ).observe(duration)

        # Track errors
        if status_code >= 400:
            self._error_count += 1
            http_errors_total.labels(
                method=method, endpoint=endpoint, status_code=str(status_code)
            ).inc()

        # Update error rate gauge periodically
        self._update_error_rate()

    def _update_error_rate(self) -> None:
        """Update error rate metrics"""
        if self._request_count > 0:
            error_rate: float = (self._error_count / self._request_count) * 100
            error_rate_gauge.labels(window="total").set(error_rate)

    def record_health_check(self, check_type: str, status: str, duration: float) -> None:
        """Record a health check result"""
        health_check_total.labels(check_type=check_type, status=status).inc()
        health_check_duration_seconds.labels(check_type=check_type).observe(duration)

    def update_component_health(self, component: str, is_healthy: bool) -> None:
        """Update individual component health status"""
        component_health_status.labels(component=component).set(1 if is_healthy else 0)

    def update_uptime(self) -> None:
        """Update uptime metrics"""
        current_uptime: float = time.time() - self._startup_time
        uptime_seconds.set(current_uptime)

        # Calculate uptime percentage
        total_time: float = current_uptime
        if total_time > 0:
            uptime_pct: float = ((total_time - self._downtime_seconds) / total_time) * 100
            current_uptime_percent.set(uptime_pct)

    def record_downtime(self, duration_seconds: float) -> None:
        """Record a period of downtime"""
        self._downtime_seconds += duration_seconds
        self.update_uptime()

    def update_latency_percentiles(self, p50: float, p95: float, p99: float) -> None:
        """Update latency percentile metrics"""
        request_latency_p50.set(p50)
        request_latency_p95.set(p95)
        request_latency_p99.set(p99)

    def record_alert(self, severity: str, alert_name: str) -> None:
        """Record an alert"""
        alerts_total.labels(severity=severity, alert_name=alert_name).inc()

    def update_firing_alerts(self, critical: int, warning: int, info: int) -> None:
        """Update currently firing alert counts"""
        alerts_firing.labels(severity="critical").set(critical)
        alerts_firing.labels(severity="warning").set(warning)
        alerts_firing.labels(severity="info").set(info)

    def get_sla_status(self) -> dict[str, float | int | bool]:
        """Get current SLA status"""
        current_uptime: float = time.time() - self._startup_time
        total_time: float = current_uptime
        uptime_pct: float | int = (
            ((total_time - self._downtime_seconds) / total_time) * 100 if total_time > 0 else 100
        )

        error_rate: float | int = (
            (self._error_count / self._request_count) * 100 if self._request_count > 0 else 0
        )

        return {
            "uptime_seconds": current_uptime,
            "uptime_percent": uptime_pct,
            "sla_target_percent": self._sla_target,
            "sla_met": uptime_pct >= self._sla_target,
            "error_rate_percent": error_rate,
            "error_rate_target": 0.1,  # <0.1% target
            "error_rate_met": error_rate < 0.1,
            "total_requests": self._request_count,
            "total_errors": self._error_count,
        }


# Global SLA monitor instance
_sla_monitor: SLAMonitor | None = None


def get_sla_monitor() -> SLAMonitor:
    """Get or create the SLA monitor singleton"""
    global _sla_monitor
    if _sla_monitor is None:
        _sla_monitor = SLAMonitor()
    return _sla_monitor


# ============================================================================
# METRICS EXPORT
# ============================================================================


def get_metrics() -> bytes:
    """
    Generate and return Prometheus metrics in text format.

    Returns:
        Metrics in Prometheus text exposition format
    """
    try:
        return generate_latest(REGISTRY)
    except Exception as e:
        logger.error(f"Error generating Prometheus metrics: {e}")
        # Return empty metrics on error
        return b""


def get_metrics_info() -> dict[str, dict[str, float | int | dict[str, float | int]]]:
    """
    Get human-readable metrics information for debugging.

    Returns:
        Dictionary with current metric values
    """
    return {
        "training": {
            "sessions_total": getattr(
                getattr(training_sessions_total, "_value", None), "get", lambda: 0
            )(),
            "average_loss": getattr(
                getattr(training_average_loss, "_value", None), "get", lambda: 0
            )(),
            "final_loss": getattr(getattr(training_final_loss, "_value", None), "get", lambda: 0)(),
        },
        "experiences": {
            "processed_total": getattr(
                getattr(experiences_processed_total, "_value", None), "get", lambda: 0
            )(),
            "transformed_total": getattr(
                getattr(experiences_transformed_total, "_value", None), "get", lambda: 0
            )(),
        },
        "mlflow": {
            "runs_created": getattr(
                getattr(mlflow_runs_created_total, "_value", None), "get", lambda: 0
            )(),
            "connection_status": getattr(
                getattr(mlflow_connection_status, "_value", None), "get", lambda: 0
            )(),
        },
        "pipeline": {
            "inference_total": {
                "success": getattr(
                    getattr(
                        pipeline_inference_total.labels(status="success"),
                        "_value",
                        None,
                    ),
                    "get",
                    lambda: 0,
                )(),
                "failure": getattr(
                    getattr(
                        pipeline_inference_total.labels(status="failure"),
                        "_value",
                        None,
                    ),
                    "get",
                    lambda: 0,
                )(),
            },
            "model_updates": getattr(
                getattr(model_update_total, "_value", None), "get", lambda: 0
            )(),
        },
    }


# ============================================================================
# FOCUS BUILDER METRICS
# ============================================================================

# Flow lifecycle metrics
focus_builder_flows_created_total: Counter = get_or_create_counter(
    "focus_builder_flows_created_total",
    "Total number of flows created",
    ["tenant_id", "status"],  # status: 'success', 'validation_error', 'sync_failed'
)

focus_builder_flows_updated_total: Counter = get_or_create_counter(
    "focus_builder_flows_updated_total",
    "Total number of flows updated",
    ["tenant_id", "status"],
)

focus_builder_flows_deleted_total: Counter = get_or_create_counter(
    "focus_builder_flows_deleted_total", "Total number of flows deleted", ["tenant_id"]
)

focus_builder_flows_executed_total: Counter = get_or_create_counter(
    "focus_builder_flows_executed_total",
    "Total number of flow executions",
    ["tenant_id", "status"],  # status: 'success', 'failed'
)

# ActivePieces integration metrics
focus_builder_activepieces_latency_seconds: Histogram = get_or_create_histogram(
    "focus_builder_activepieces_latency_seconds",
    "ActivePieces API call latency in seconds",
    labelnames=["operation"],  # operation: 'create', 'update', 'delete', 'execute', 'list_pieces'
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

focus_builder_activepieces_errors_total: Counter = get_or_create_counter(
    "focus_builder_activepieces_errors_total",
    "Total ActivePieces API errors",
    [
        "operation",
        "error_type",
    ],  # error_type: 'http_error', 'timeout', 'connection_error'
)

focus_builder_activepieces_status: Gauge = get_or_create_gauge(
    "focus_builder_activepieces_status",
    "ActivePieces connectivity status (1=connected, 0=disconnected)",
)

# Graph validation metrics
focus_builder_validation_errors_total: Counter = get_or_create_counter(
    "focus_builder_validation_errors_total",
    "Total graph validation errors",
    ["error_type"],  # error_type: 'cycle', 'missing_trigger', 'orphan_node', 'limit_exceeded'
)

# Pieces catalog metrics
focus_builder_pieces_cache_size: Gauge = get_or_create_gauge(
    "focus_builder_pieces_cache_size", "Number of pieces in local cache"
)

focus_builder_pieces_sync_total: Counter = get_or_create_counter(
    "focus_builder_pieces_sync_total",
    "Total pieces catalog syncs",
    ["status"],  # status: 'success', 'failed'
)

focus_builder_pieces_sync_duration_seconds: Histogram = get_or_create_histogram(
    "focus_builder_pieces_sync_duration_seconds",
    "Duration of pieces catalog sync in seconds",
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# AI suggestion metrics
focus_builder_suggestions_total: Counter = get_or_create_counter(
    "focus_builder_suggestions_total",
    "Total AI node suggestion requests",
    ["tenant_id", "cache_hit"],  # cache_hit: 'true', 'false'
)

focus_builder_suggestions_latency_seconds: Histogram = get_or_create_histogram(
    "focus_builder_suggestions_latency_seconds",
    "AI suggestion request latency in seconds",
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)


# ============================================================================
# FOCUS BUILDER HELPER FUNCTIONS
# ============================================================================


def record_flow_created(tenant_id: int, status: str = "success") -> None:
    """Record a flow creation."""
    focus_builder_flows_created_total.labels(tenant_id=str(tenant_id), status=status).inc()


def record_flow_updated(tenant_id: int, status: str = "success") -> None:
    """Record a flow update."""
    focus_builder_flows_updated_total.labels(tenant_id=str(tenant_id), status=status).inc()


def record_flow_deleted(tenant_id: int) -> None:
    """Record a flow deletion."""
    focus_builder_flows_deleted_total.labels(tenant_id=str(tenant_id)).inc()


def record_flow_executed(tenant_id: int, status: str = "success") -> None:
    """Record a flow execution."""
    focus_builder_flows_executed_total.labels(tenant_id=str(tenant_id), status=status).inc()


def record_activepieces_latency(operation: str, duration_seconds: float) -> None:
    """Record ActivePieces API latency."""
    focus_builder_activepieces_latency_seconds.labels(operation=operation).observe(duration_seconds)


def record_activepieces_error(operation: str, error_type: str) -> None:
    """Record an ActivePieces API error."""
    focus_builder_activepieces_errors_total.labels(operation=operation, error_type=error_type).inc()


def set_activepieces_status(connected: bool) -> None:
    """Set ActivePieces connectivity status."""
    focus_builder_activepieces_status.set(1 if connected else 0)


def record_validation_error(error_type: str) -> None:
    """Record a graph validation error."""
    focus_builder_validation_errors_total.labels(error_type=error_type).inc()


def set_pieces_cache_size(count: int) -> None:
    """Set the pieces cache size."""
    focus_builder_pieces_cache_size.set(count)


def record_pieces_sync(status: str, duration_seconds: float) -> None:
    """Record a pieces catalog sync."""
    focus_builder_pieces_sync_total.labels(status=status).inc()
    focus_builder_pieces_sync_duration_seconds.observe(duration_seconds)


def record_suggestion_request(tenant_id: int, cache_hit: bool, duration_seconds: float) -> None:
    """Record an AI suggestion request."""
    focus_builder_suggestions_total.labels(
        tenant_id=str(tenant_id), cache_hit="true" if cache_hit else "false"
    ).inc()
    focus_builder_suggestions_latency_seconds.observe(duration_seconds)


# ============================================================================
# LEARNING METRICS HELPER FUNCTIONS
# ============================================================================


def record_learning_observation(tenant_id: int, learning_type: str) -> None:
    """Record a learning observation.

    Args:
        tenant_id: The tenant ID
        learning_type: Type of learning (PERFORMANCE_OPTIMIZATION, ERROR_RECOVERY, etc.)
    """
    learning_observations_total.labels(
        tenant_id=str(tenant_id),
        learning_type=learning_type,
    ).inc()


def update_learning_patterns_active(tenant_id: int, count: int) -> None:
    """Update the number of active learning patterns.

    Args:
        tenant_id: The tenant ID
        count: Number of active patterns
    """
    learning_patterns_active.labels(tenant_id=str(tenant_id)).set(count)


def record_learning_adaptation_applied(tenant_id: int, outcome: str) -> None:
    """Record that a learning adaptation was applied.

    Args:
        tenant_id: The tenant ID
        outcome: Outcome of the adaptation ('success', 'failure', 'partial')
    """
    learning_adaptation_applied.labels(
        tenant_id=str(tenant_id),
        outcome=outcome,
    ).inc()


def record_learning_cross_agent_share(
    tenant_id: int, source_agent_type: str, target_agent_type: str
) -> None:
    """Record a cross-agent learning share.

    Args:
        tenant_id: The tenant ID
        source_agent_type: Source agent type that learned the pattern
        target_agent_type: Target agent type that received the pattern
    """
    learning_cross_agent_shares.labels(
        tenant_id=str(tenant_id),
        source_agent_type=source_agent_type,
        target_agent_type=target_agent_type,
    ).inc()


# ============================================================================
# INITIALIZATION
# ============================================================================


def initialize_metrics() -> None:
    """
    Initialize metrics with default values.
    Should be called at service startup.
    """
    logger.info("Initializing Prometheus metrics for training service")

    # Set default health status
    set_training_service_health(True)
    set_training_service_ready(False)

    # Set default MLflow connection status
    set_mlflow_connection_status(False)

    logger.info("Prometheus metrics initialized successfully")


# Auto-initialize on module import
initialize_metrics()
