"""
AgentMetricsCollector for Agentic Domain

Collects Prometheus metrics specific to the agentic system:
- Chat request counts and latencies per feature
- Token usage (input/output)
- User satisfaction scores
- Feature detection layer usage
- Active sessions per tenant
"""

import logging
from typing import Any, Optional, cast

from prometheus_client import REGISTRY, Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Cache for metrics to prevent duplicate registration
_metrics_cache: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type


def _get_or_create_counter(name: str, description: str, labels: list[str]) -> Counter:
    """Get existing counter or create new one (singleton-safe for test reloads)."""
    global _metrics_cache

    if name in _metrics_cache:
        return cast(Counter, _metrics_cache[name])

    try:
        # Check registry for existing metric (handles _total, _created suffixes)
        names_to_collectors: dict[str, Any] = getattr(REGISTRY, "_names_to_collectors", {})  # TODO(TYPE): replace Any with concrete type
        collectors = list(names_to_collectors.values())
        for collector in collectors:
            collector_name = getattr(collector, "_name", None)
            if collector_name == name:
                _metrics_cache[name] = collector
                return cast(Counter, collector)

        # Check with _total suffix (Prometheus convention for counters)
        for collector in collectors:
            collector_name = getattr(collector, "_name", None)
            if collector_name == f"{name}_total" or collector_name == name.replace("_total", ""):
                _metrics_cache[name] = collector
                return cast(Counter, collector)

        # Create new counter
        metric = Counter(name, description, labels, registry=REGISTRY)
        _metrics_cache[name] = metric
        return metric
    except ValueError as e:
        # Already exists with different config - find and return existing
        if "Duplicated" in str(e):
            names_to_collectors_fb: dict[str, Any] = getattr(REGISTRY, "_names_to_collectors", {})  # TODO(TYPE): replace Any with concrete type
            for collector in list(names_to_collectors_fb.values()):
                coll_name = getattr(collector, "_name", "")
                if coll_name and name in coll_name:
                    _metrics_cache[name] = collector
                    return cast(Counter, collector)
        raise


def _get_or_create_histogram(
    name: str, description: str, labels: list[str], buckets: list[float] | None = None
) -> Histogram:
    """Get existing histogram or create new one (singleton-safe for test reloads)."""
    global _metrics_cache

    if name in _metrics_cache:
        return cast(Histogram, _metrics_cache[name])

    try:
        # Check registry for existing metric
        names_to_collectors: dict[str, Any] = getattr(REGISTRY, "_names_to_collectors", {})  # TODO(TYPE): replace Any with concrete type
        for collector in list(names_to_collectors.values()):
            collector_name = getattr(collector, "_name", None)
            if collector_name == name:
                _metrics_cache[name] = collector
                return cast(Histogram, collector)

        # Create new histogram
        if buckets:
            metric = Histogram(name, description, labels, buckets=buckets, registry=REGISTRY)
        else:
            metric = Histogram(name, description, labels, registry=REGISTRY)
        _metrics_cache[name] = metric
        return metric
    except ValueError as e:
        if "Duplicated" in str(e):
            names_to_collectors_fb: dict[str, Any] = getattr(REGISTRY, "_names_to_collectors", {})  # TODO(TYPE): replace Any with concrete type
            for collector in list(names_to_collectors_fb.values()):
                coll_name = getattr(collector, "_name", "")
                if coll_name and name in coll_name:
                    _metrics_cache[name] = collector
                    return cast(Histogram, collector)
        raise


def _get_or_create_gauge(name: str, description: str, labels: list[str] | None = None) -> Gauge:
    """Get existing gauge or create new one (singleton-safe for test reloads)."""
    global _metrics_cache

    if name in _metrics_cache:
        return cast(Gauge, _metrics_cache[name])

    try:
        # Check registry for existing metric
        names_to_collectors: dict[str, Any] = getattr(REGISTRY, "_names_to_collectors", {})  # TODO(TYPE): replace Any with concrete type
        for collector in list(names_to_collectors.values()):
            collector_name = getattr(collector, "_name", None)
            if collector_name == name:
                _metrics_cache[name] = collector
                return cast(Gauge, collector)

        # Create new gauge
        if labels:
            metric = Gauge(name, description, labels, registry=REGISTRY)
        else:
            metric = Gauge(name, description, registry=REGISTRY)
        _metrics_cache[name] = metric
        return metric
    except ValueError as e:
        if "Duplicated" in str(e):
            names_to_collectors_fb: dict[str, Any] = getattr(REGISTRY, "_names_to_collectors", {})  # TODO(TYPE): replace Any with concrete type
            for collector in list(names_to_collectors_fb.values()):
                coll_name = getattr(collector, "_name", "")
                if coll_name and name in coll_name:
                    _metrics_cache[name] = collector
                    return cast(Gauge, collector)
        raise


class AgentMetricsCollector:
    """
    Collects and exposes Prometheus metrics for the agentic system.

    Metrics:
    - agent_requests_total: Counter of chat requests by feature, tenant, status
    - agent_request_duration_seconds: Histogram of request latencies
    - agent_tokens_total: Counter of tokens used (input/output)
    - prompt_satisfaction: Histogram of user satisfaction scores (1-5)
    - feature_detection_layer: Counter of which detection layer was used
    - active_sessions: Gauge of current active sessions per tenant
    """

    def __init__(self) -> None:
        """Initialize metrics collectors."""
        # Chat request metrics
        self._requests_total = _get_or_create_counter(
            "agent_requests_total",
            "Total agent chat requests",
            ["feature", "tenant_id", "status"],
        )

        self._request_duration = _get_or_create_histogram(
            "agent_request_duration_seconds",
            "Agent request duration in seconds",
            ["feature"],
            buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )

        # Token usage metrics
        self._tokens_total = _get_or_create_counter(
            "agent_tokens_total",
            "Total tokens used by agent",
            ["feature", "direction"],  # direction: input/output
        )

        # User satisfaction metrics
        self._satisfaction = _get_or_create_histogram(
            "prompt_satisfaction",
            "User satisfaction scores (1-5)",
            ["feature", "variant"],
            buckets=[1, 2, 3, 4, 5],
        )

        # Feature detection metrics
        self._detection_layer = _get_or_create_counter(
            "feature_detection_layer",
            "Which detection layer was used for feature routing",
            ["layer"],  # header, route, session, llm
        )

        # Active sessions gauge
        self._active_sessions = _get_or_create_gauge(
            "active_sessions", "Current active agent sessions", ["tenant_id"]
        )

        logger.debug("AgentMetricsCollector initialized")

    def record_chat_request(
        self, feature: str, tenant_id: str, duration: float, success: bool
    ) -> None:
        """
        Record a chat request with its metrics.

        Args:
            feature: Feature context (e.g., "assistant", "code_assistant")
            tenant_id: Tenant identifier
            duration: Request duration in seconds
            success: Whether the request completed successfully
        """
        status = "success" if success else "failure"

        # Increment request counter
        self._requests_total.labels(feature=feature, tenant_id=tenant_id, status=status).inc()

        # Observe duration
        self._request_duration.labels(feature=feature).observe(duration)

        logger.debug(
            f"Recorded chat request: feature={feature}, status={status}, duration={duration:.3f}s"
        )

    def record_token_usage(self, feature: str, input_tokens: int, output_tokens: int) -> None:
        """
        Record token usage for a request.

        Args:
            feature: Feature context
            input_tokens: Number of input tokens (prompt)
            output_tokens: Number of output tokens (response)
        """
        # Clamp negative values to 0 (counters can only increment by non-negative amounts)
        safe_input = max(0, input_tokens) if input_tokens is not None else 0
        safe_output = max(0, output_tokens) if output_tokens is not None else 0

        self._tokens_total.labels(feature=feature, direction="input").inc(safe_input)

        self._tokens_total.labels(feature=feature, direction="output").inc(safe_output)

        logger.debug(f"Recorded tokens: feature={feature}, in={safe_input}, out={safe_output}")

    def record_satisfaction(self, feature: str, variant: str, score: int) -> None:
        """
        Record user satisfaction score.

        Args:
            feature: Feature context
            variant: Prompt variant name
            score: Satisfaction score (1-5)
        """
        # Clamp score to valid range
        clamped_score = max(1, min(5, score))

        self._satisfaction.labels(feature=feature, variant=variant).observe(clamped_score)

        logger.debug(
            f"Recorded satisfaction: feature={feature}, variant={variant}, score={clamped_score}"
        )

    def record_feature_detection(self, layer: str) -> None:
        """
        Record which detection layer was used for feature routing.

        Args:
            layer: Detection layer (header, route, session, llm)
        """
        valid_layers = ["header", "route", "session", "llm"]
        if layer not in valid_layers:
            logger.warning(f"Invalid detection layer: {layer}")
            layer = "unknown"

        self._detection_layer.labels(layer=layer).inc()

        logger.debug(f"Recorded feature detection: layer={layer}")

    def update_active_sessions(self, tenant_id: str, count: int) -> None:
        """
        Update the active sessions gauge for a tenant.

        Args:
            tenant_id: Tenant identifier
            count: Current number of active sessions
        """
        self._active_sessions.labels(tenant_id=tenant_id).set(count)

        logger.debug(f"Updated active sessions: tenant={tenant_id}, count={count}")

    def get_metrics_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get a summary of all registered metrics.

        Returns: Dict[str, Any]ionary with metric names and basic info  # TODO(TYPE): replace Any with concrete type
        """
        return {
            "agent_requests_total": {
                "type": "counter",
                "description": "Total agent chat requests",
            },
            "agent_request_duration_seconds": {
                "type": "histogram",
                "description": "Agent request duration",
            },
            "agent_tokens_total": {
                "type": "counter",
                "description": "Total tokens used",
            },
            "prompt_satisfaction": {
                "type": "histogram",
                "description": "User satisfaction scores",
            },
            "feature_detection_layer": {
                "type": "counter",
                "description": "Feature detection layer usage",
            },
            "active_sessions": {
                "type": "gauge",
                "description": "Active sessions per tenant",
            },
        }


# Singleton instance
agent_metrics = AgentMetricsCollector()
