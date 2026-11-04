"""
Tenant-Aware Metrics Collection

Provides:
- Per-tenant Prometheus metrics
- Request/error/token tracking
- SLA compliance monitoring
"""

import time
from typing import Any, Dict, Optional, Set, Type, Union


class TenantMetricsCollector:
    """
    Collects metrics per tenant for multi-tenant observability.
    """

    def __init__(self, registry: Any | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Initialize metrics collector.

        Args:
            registry: Prometheus registry (optional)
        """
        self._registry = registry
        self._counters: dict[str, dict[str, int | float]] = {}
        self._histograms: dict[str, dict[str, list[float]]] = {}
        self._gauges: dict[str, dict[str, float]] = {}

    def record_request(
        self,
        tenant_id: int,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """
        Record HTTP request metrics.

        Args:
            tenant_id: Tenant ID
            endpoint: API endpoint
            method: HTTP method
            status_code: Response status code
            duration_ms: Request duration in milliseconds
        """
        tenant_key = str(tenant_id)

        # Initialize tenant counters
        if tenant_key not in self._counters:
            self._counters[tenant_key] = {}

        # Count request
        counter_key = f"requests_total:{method}:{endpoint}:{status_code}"
        self._counters[tenant_key][counter_key] = self._counters[tenant_key].get(counter_key, 0) + 1

        # Track duration
        if tenant_key not in self._histograms:
            self._histograms[tenant_key] = {}

        hist_key = f"request_duration:{endpoint}"
        if hist_key not in self._histograms[tenant_key]:
            self._histograms[tenant_key][hist_key] = []
        self._histograms[tenant_key][hist_key].append(duration_ms)

    def record_error(
        self,
        tenant_id: int,
        error_type: str,
        endpoint: str | None = None,
    ) -> None:
        """
        Record error metric.

        Args:
            tenant_id: Tenant ID
            error_type: Error type/class
            endpoint: API endpoint where error occurred
        """
        tenant_key = str(tenant_id)

        if tenant_key not in self._counters:
            self._counters[tenant_key] = {}

        counter_key = f"errors_total:{error_type}"
        if endpoint:
            counter_key += f":{endpoint}"

        self._counters[tenant_key][counter_key] = self._counters[tenant_key].get(counter_key, 0) + 1

    def record_tokens(
        self,
        tenant_id: int,
        agent_type: str,
        model: str,
        tokens_used: int,
        cost_usd: float,
    ) -> None:
        """
        Record token usage metrics.

        Args:
            tenant_id: Tenant ID
            agent_type: Type of agent
            model: LLM model name
            tokens_used: Number of tokens used
            cost_usd: Cost in USD
        """
        tenant_key = str(tenant_id)

        if tenant_key not in self._counters:
            self._counters[tenant_key] = {}

        # Token counter
        token_key = f"tokens_used_total:{agent_type}:{model}"
        self._counters[tenant_key][token_key] = (
            self._counters[tenant_key].get(token_key, 0) + tokens_used
        )

        # Cost counter
        cost_key = f"cost_usd_total:{agent_type}"
        current_cost = self._counters[tenant_key].get(cost_key, 0)
        self._counters[tenant_key][cost_key] = current_cost + cost_usd

    def set_gauge(
        self,
        tenant_id: int,
        metric_name: str,
        value: float,
    ) -> None:
        """
        Set gauge value.

        Args:
            tenant_id: Tenant ID
            metric_name: Name of gauge metric
            value: Gauge value
        """
        tenant_key = str(tenant_id)

        if tenant_key not in self._gauges:
            self._gauges[tenant_key] = {}

        self._gauges[tenant_key][metric_name] = value

    def record_agent_execution(
        self,
        tenant_id: int,
        agent_type: str,
        duration_ms: float,
    ) -> None:
        """
        Record agent execution metrics.

        Args:
            tenant_id: Tenant ID
            agent_type: Agent type
            duration_ms: Execution duration
        """
        tenant_key = str(tenant_id)

        if tenant_key not in self._histograms:
            self._histograms[tenant_key] = {}

        hist_key = f"agent_execution:{agent_type}"
        if hist_key not in self._histograms[tenant_key]:
            self._histograms[tenant_key][hist_key] = []

        self._histograms[tenant_key][hist_key].append(duration_ms)

    def get_tenant_metrics(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get all metrics for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns: Dict[str, Any]ionary with all tenant metrics  # TODO(TYPE): replace Any with concrete type
        """
        tenant_key = str(tenant_id)

        metrics = {
            "tenant_id": tenant_id,
            "counters": self._counters.get(tenant_key, {}),
            "gauges": self._gauges.get(tenant_key, {}),
        }

        # Calculate histogram statistics
        histograms = self._histograms.get(tenant_key, {})
        hist_stats: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key, values in histograms.items():
            if values:
                sorted_values = sorted(values)
                hist_stats[key] = {
                    "count": len(values),
                    "sum": sum(values),
                    "avg": sum(values) / len(values),
                    "p50": sorted_values[len(values) // 2],
                    "p95": (
                        sorted_values[int(len(values) * 0.95)]
                        if len(values) >= 20
                        else sorted_values[-1]
                    ),
                    "p99": (
                        sorted_values[int(len(values) * 0.99)]
                        if len(values) >= 100
                        else sorted_values[-1]
                    ),
                }

        metrics["histograms"] = hist_stats

        return metrics

    def get_error_rate(self, tenant_id: int, window_size: int = 100) -> float:
        """
        Calculate error rate for tenant.

        Args:
            tenant_id: Tenant ID
            window_size: Number of recent requests to consider

        Returns:
            Error rate (0.0 - 1.0)
        """
        tenant_key = str(tenant_id)
        counters = self._counters.get(tenant_key, {})

        total_requests = sum(v for k, v in counters.items() if k.startswith("requests_total:"))
        total_errors = sum(v for k, v in counters.items() if k.startswith("errors_total:"))

        if total_requests == 0:
            return 0.0

        return total_errors / total_requests


class TenantMetricsMiddleware:
    """
    Middleware for collecting tenant metrics.
    """

    def __init__(self, collector: TenantMetricsCollector) -> None:
        self.collector = collector
        self._active_requests: dict[tuple[int, str, str], float] = {}

    async def process_request(
        self,
        tenant_id: int,
        endpoint: str,
        method: str,
    ) -> None:
        """Process incoming request (record start timing)."""
        self._active_requests[(tenant_id, endpoint, method)] = time.monotonic()

    async def process_response(
        self,
        tenant_id: int,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        """Process response (record metrics)."""
        self._active_requests.pop((tenant_id, endpoint, method), None)
        self.collector.record_request(
            tenant_id=tenant_id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
        )

        # Record error if applicable
        if status_code >= 400:
            error_type = "client_error" if status_code < 500 else "server_error"
            self.collector.record_error(
                tenant_id=tenant_id,
                error_type=error_type,
                endpoint=endpoint,
            )
