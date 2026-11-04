# core/middleware/metrics_middleware.py
"""
Prometheus Metrics Middleware for Tool Broker Service

Collects detailed metrics for:
- Request latency (by endpoint and method)
- Request count (by endpoint, method, and status code)
- Active request tracking
- Error rate monitoring
- Tool execution metrics
"""

import logging
import time
from typing import Any, Optional, cast
from collections.abc import Callable

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    REGISTRY,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Prometheus Metrics for Tool Broker

# Request latency histogram (in seconds)
REQUEST_LATENCY = Histogram(
    "tool_broker_request_latency_seconds",
    "Tool Broker request latency in seconds",
    ["endpoint", "method"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Request count counter
REQUEST_COUNT = Counter(
    "tool_broker_requests_total",
    "Total Tool Broker requests",
    ["endpoint", "method", "status_code"],
)

# Active requests gauge
ACTIVE_REQUESTS = Gauge(
    "tool_broker_active_requests", "Active Tool Broker requests", ["endpoint", "method"]
)

# HTTP error counter
HTTP_ERRORS = Counter(
    "tool_broker_http_errors_total",
    "Total HTTP errors in Tool Broker",
    ["endpoint", "method", "status_code"],
)

# Tool execution counter (by tool name and status)
TOOL_EXECUTION_COUNT = Counter(
    "tool_broker_tool_executions_total",
    "Total Tool Broker tool executions",
    ["tool_name", "status"],
)

# Tool execution latency histogram
TOOL_EXECUTION_LATENCY = Histogram(
    "tool_broker_tool_execution_latency_seconds",
    "Tool Broker tool execution latency in seconds",
    ["tool_name"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

# DI Container initialization counter
DI_CONTAINER_INITIALIZATIONS = Counter(
    "tool_broker_di_container_initializations_total",
    "Total Tool Broker DI container initializations",
)

# Service health gauge (1 = healthy, 0 = unhealthy)
SERVICE_HEALTH = Gauge(
    "tool_broker_service_health",
    "Tool Broker service health status (1=healthy, 0=unhealthy)",
    ["service_name"],
)

# Client connection gauge
CLIENT_CONNECTIONS = Gauge(
    "tool_broker_client_connections",
    "Tool Broker client connections status (1=connected, 0=disconnected)",
    ["client_name"],
)


class ToolBrokerMetricsMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for collecting Tool Broker metrics

    Features:
    - Request latency tracking
    - Request/response counting
    - Active request tracking
    - Error rate monitoring
    - Endpoint-level metrics
    """

    def __init__(self, app: ASGIApp, skip_paths: list[str] | None = None) -> None:
        """
        Initialize metrics middleware

        Args:
            app: ASGI application
            skip_paths: list[Any] of path patterns to skip metrics collection  # TODO(TYPE): replace Any with concrete type
        """
        super().__init__(app)
        self.skip_paths = skip_paths or ["/health", "/metrics", "/docs", "/redoc"]
        logger.info("ToolBrokerMetricsMiddleware initialized")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    def _should_skip_metrics(self, path: str) -> bool:
        """Check if path should be skipped from metrics collection"""
        return any(path.startswith(skip) for skip in self.skip_paths)

    async def dispatch(self, request: Request, call_next: Callable[..., Any]) -> Response:  # TODO(TYPE): replace Any with concrete type
        """
        Process request and collect metrics

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response from handler
        """
        path = request.url.path
        method = request.method

        # Skip metrics collection for health check endpoints
        if self._should_skip_metrics(path):
            return cast(Response, await call_next(request))

        # Normalize endpoint path (remove IDs to avoid metric explosion)
        endpoint = self._normalize_path(path)

        # Track active requests
        ACTIVE_REQUESTS.labels(endpoint=endpoint, method=method).inc()

        # Record request start time
        start_time = time.time()

        try:
            # Process request
            response = cast(Response, await call_next(request))

            # Measure latency
            latency = time.time() - start_time
            REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(latency)

            # Count request
            REQUEST_COUNT.labels(
                endpoint=endpoint, method=method, status_code=response.status_code
            ).inc()

            # Track errors
            if response.status_code >= 400:
                HTTP_ERRORS.labels(
                    endpoint=endpoint, method=method, status_code=response.status_code
                ).inc()

            logger.debug(
                f"Request completed: {method} {path} -> {response.status_code} ({latency:.3f}s)"
            )

            return response

        except Exception as e:
            # Record error
            latency = time.time() - start_time
            REQUEST_LATENCY.labels(endpoint=endpoint, method=method).observe(latency)
            REQUEST_COUNT.labels(endpoint=endpoint, method=method, status_code=500).inc()
            HTTP_ERRORS.labels(endpoint=endpoint, method=method, status_code=500).inc()

            logger.error(f"Request error: {method} {path} - {str(e)}")
            raise

        finally:
            # Decrement active requests
            ACTIVE_REQUESTS.labels(endpoint=endpoint, method=method).dec()

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path to avoid metric explosion from IDs

        Examples:
            /v1/tools/execute -> /v1/tools/execute
            /api/v1/tasks/123 -> /api/v1/tasks/{id}
            /api/v1/tasks/abc-def/status -> /api/v1/tasks/{id}/status
        """
        parts = path.split("/")
        normalized_parts: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for part in parts:
            # Check if part looks like an ID
            if part and self._looks_like_id(part):
                normalized_parts.append("{id}")
            else:
                normalized_parts.append(part)

        return "/".join(normalized_parts)

    def _looks_like_id(self, part: str) -> bool:
        """
        Determine if a path segment looks like an ID
        Pure numeric, UUID, or hash format - not names/slugs
        """
        if not part:
            return False

        # Pure numeric ID
        if part.isdigit():
            return True

        # UUID format (8-4-4-4-12)
        if len(part) == 36 and part.count("-") == 4:
            return True

        # Long hash-like with multiple hyphens
        if len(part) > 15 and part.count("-") > 1:
            return True

        return False


class ToolBrokerServiceMetricsCollector:
    """
    Utility class for collecting Tool Broker service-level metrics
    """

    @staticmethod
    def record_tool_execution(tool_name: str, success: bool, duration: float) -> None:
        """
        Record tool execution metrics

        Args:
            tool_name: Name of executed tool
            success: Whether execution succeeded
            duration: Execution duration in seconds
        """
        status = "success" if success else "failure"
        TOOL_EXECUTION_COUNT.labels(tool_name=tool_name, status=status).inc()
        TOOL_EXECUTION_LATENCY.labels(tool_name=tool_name).observe(duration)

        logger.debug(f"Tool execution: {tool_name} - {status} ({duration:.3f}s)")

    @staticmethod
    def record_di_container_initialization() -> None:
        """Record DI container initialization"""
        DI_CONTAINER_INITIALIZATIONS.inc()
        logger.info("DI container initialization recorded")

    @staticmethod
    def set_service_health(service_name: str, is_healthy: bool) -> None:
        """
        Set service health status

        Args:
            service_name: Name of service
            is_healthy: Health status
        """
        health_value = 1.0 if is_healthy else 0.0
        SERVICE_HEALTH.labels(service_name=service_name).set(health_value)
        logger.info(f"Service health updated: {service_name}={health_value}")

    @staticmethod
    def set_client_connection(client_name: str, is_connected: bool) -> None:
        """
        Set client connection status

        Args:
            client_name: Name of client
            is_connected: Connection status
        """
        connection_value = 1.0 if is_connected else 0.0
        CLIENT_CONNECTIONS.labels(client_name=client_name).set(connection_value)
        logger.info(f"Client connection updated: {client_name}={connection_value}")


def get_prometheus_registry() -> CollectorRegistry:
    """
    Get configured Prometheus registry with Tool Broker metrics

    Returns:
        Prometheus CollectorRegistry with all Tool Broker metrics
    """

    # Metrics are automatically registered when created above
    return REGISTRY


def generate_metrics_response() -> str:
    """
    Generate Prometheus metrics response

    Returns:
        Formatted metrics string for /metrics endpoint
    """

    metrics_output = generate_latest(get_prometheus_registry())
    return metrics_output.decode("utf-8")
