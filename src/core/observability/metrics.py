"""
Prometheus Metrics Definition
Tracks API usage, latency, and errors with tenant context.

Context7 Best Practice: /prometheus/client_python
- MultiProcessCollector for Gunicorn multi-worker environments
- ProcessCollector for CPU, memory, file descriptors
- PlatformCollector for platform-specific metrics
"""

import os
import re
import time
from typing import Any, cast

from prometheus_client import (
    REGISTRY,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    PlatformCollector,
    ProcessCollector,
)
from prometheus_client.multiprocess import MultiProcessCollector
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.middleware.tenant_context import get_tenant_id

# ==================== REGISTRY SETUP (Context7 Pattern) ====================

# Use custom registry for multi-process mode
if "PROMETHEUS_MULTIPROC_DIR" in os.environ:
    # Multi-process mode (Gunicorn with multiple workers)
    registry = CollectorRegistry()
    MultiProcessCollector(registry)  # type: ignore[no-untyped-call]

    # Add process and platform collectors (Context7 best practice)
    ProcessCollector(namespace="sanskritisetu", registry=registry)
    PlatformCollector(registry=registry)
else:
    # Single-process mode (development)
    registry = REGISTRY


def _get_or_create_counter(name: str, description: str, labels: list[str]) -> Counter:
    """Get existing counter or create new one (singleton-safe for test reloads)."""
    try:
        # Try to get existing metric from registry
        names_to_collectors: dict[str, Any] = (  # TODO(TYPE): replace Any with concrete type
            getattr(  # TODO(TYPE): Any -- prometheus internal registry: str->Collector
                registry, "_names_to_collectors", {}
            )
        )
        for collector in list(names_to_collectors.values()):
            if getattr(collector, "_name", None) == name:
                return cast(Counter, collector)
        # Create new counter if not exists
        return Counter(name, description, labels, registry=registry)
    except Exception:
        # Fallback: create new counter
        return Counter(name, description, labels, registry=registry)


def _get_or_create_histogram(name: str, description: str, labels: list[str]) -> Histogram:
    """Get existing histogram or create new one (singleton-safe for test reloads)."""
    try:
        # Try to get existing metric from registry
        names_to_collectors: dict[str, Any] = (  # TODO(TYPE): replace Any with concrete type
            getattr(  # TODO(TYPE): Any -- prometheus internal registry: str->Collector
                registry, "_names_to_collectors", {}
            )
        )
        for collector in list(names_to_collectors.values()):
            if getattr(collector, "_name", None) == name:
                return cast(Histogram, collector)
        # Create new histogram if not exists
        return Histogram(name, description, labels, registry=registry)
    except Exception:
        # Fallback: create new histogram
        return Histogram(name, description, labels, registry=registry)


def _get_or_create_gauge(name: str, description: str, labels: list[str] | None = None) -> Gauge:
    """Get existing gauge or create new one (singleton-safe for test reloads)."""
    try:
        # Try to get existing metric from registry
        names_to_collectors: dict[str, Any] = (  # TODO(TYPE): replace Any with concrete type
            getattr(  # TODO(TYPE): Any -- prometheus internal registry: str->Collector
                registry, "_names_to_collectors", {}
            )
        )
        for collector in list(names_to_collectors.values()):
            if getattr(collector, "_name", None) == name:
                return cast(Gauge, collector)
        # Create new gauge if not exists
        if labels:
            return Gauge(name, description, labels, registry=registry)
        else:
            return Gauge(name, description, registry=registry)
    except Exception:
        # Fallback: create new gauge
        if labels:
            return Gauge(name, description, labels, registry=registry)
        else:
            return Gauge(name, description, registry=registry)


# Stale Task Cleanup Metrics
STALE_CLEANUP_RUNS_TOTAL = _get_or_create_counter(
    "stale_cleanup_runs_total",
    "Total number of stale task cleanup runs",
    [],
)
STALE_CLEANUP_TASKS_FAILED_TOTAL = _get_or_create_counter(
    "stale_cleanup_tasks_failed_total",
    "Total number of tasks marked as failed by stale cleanup",
    [],
)
STALE_CLEANUP_ERRORS_TOTAL = _get_or_create_counter(
    "stale_cleanup_errors_total",
    "Total number of stale task cleanup failures",
    [],
)

SEARCH_CROSS_TENANT_LEAKAGE_DETECTED_TOTAL = _get_or_create_counter(
    "search_cross_tenant_leakage_detected_total",
    "Number of cross-tenant search results detected and filtered",
    ["source"],  # vector, bm25, fusion
)

# Metrics Definitions (singleton-safe)
REQUEST_COUNT = _get_or_create_counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code", "tenant_id"],
)

REQUEST_LATENCY = _get_or_create_histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "tenant_id"],
)

# Task 5.10: Error Rate & SLA Monitoring
HTTP_ERRORS_TOTAL = _get_or_create_counter(
    "http_errors_total", "Total HTTP errors", ["method", "endpoint", "status_code"]
)

AGENT_EXECUTION_FAILURES_TOTAL = _get_or_create_counter(
    "sanskritisetu_agent_execution_failures_total",
    "Total number of times an agent failed to execute a task",
    ["agent_id", "tenant_id", "reason"],
)

UPTIME_SECONDS = _get_or_create_gauge("uptime_seconds", "Service uptime in seconds")

# ==================== SLICE 2: Procedure-Specific Metrics ====================
# Sprint 4 - S4.2: Prometheus metrics for procedure execution tracking

PROCEDURE_EXECUTIONS_TOTAL = _get_or_create_counter(
    "procedure_executions_total",
    "Total procedure executions",
    ["tenant_id", "procedure_name", "status"],
)

PROCEDURE_EXECUTION_DURATION = _get_or_create_histogram(
    "procedure_execution_duration_seconds",
    "Procedure execution duration in seconds",
    ["tenant_id", "procedure_name"],
)

PROCEDURE_QUEUE_DEPTH = _get_or_create_gauge(
    "procedure_queue_depth", "Number of pending procedure executions", ["tenant_id"]
)

PROCEDURE_STEP_DURATION = _get_or_create_histogram(
    "procedure_step_duration_seconds",
    "Step execution duration in seconds",
    ["tenant_id", "procedure_name", "step_name", "step_type"],
)

# ==================== END SLICE 2 ====================

# ==================== SLICE 3: AI Quality Metrics ====================
# Sprint 4 - S4.3: AI quality metric collectors

AI_INTENT_MATCH_ACCURACY = _get_or_create_gauge(
    "sanskritisetu_ai_intent_match_accuracy",
    "AI intent matching accuracy (ratio of auto-selected vs user-override)",
    ["tenant_id"],
)

AI_HALLUCINATION_RATE = _get_or_create_gauge(
    "sanskritisetu_ai_hallucination_rate",
    "Rate of AI hallucinations (matched deleted/invalid procedures)",
    ["tenant_id"],
)

AI_USER_OVERRIDE_RATE = _get_or_create_gauge(
    "sanskritisetu_ai_user_override_rate",
    "Rate of user overrides of AI suggestions",
    ["tenant_id"],
)

# ==================== END SLICE 3 ====================

# ==================== CriticAgent Metrics ====================

critique_score_histogram = _get_or_create_histogram(
    "sanskritisetu_critique_score",
    "Distribution of CriticAgent critique scores",
    ["tenant_id", "mode"],
)

critique_latency_seconds = _get_or_create_histogram(
    "sanskritisetu_critique_latency_seconds",
    "CriticAgent critique_task() wall-clock latency in seconds",
    ["mode"],
)

critique_panel_invocations_total = _get_or_create_counter(
    "sanskritisetu_critique_panel_invocations_total",
    "Number of judge panel activations in CriticAgent",
    ["tenant_id"],
)

# ==================== END CriticAgent Metrics ====================

# ==================== AgentRouterAgent / MasterOrchestratorAgent Metrics ====================

agent_router_decision_latency_seconds = _get_or_create_histogram(
    "sanskritisetu_agent_router_decision_latency_seconds",
    "AgentRouterAgent.route() latency by resolving tier",
    ["tenant_id", "tier"],
)

agent_router_cache_result_total = _get_or_create_counter(
    "sanskritisetu_agent_router_cache_result_total",
    "AgentRouterAgent cache tier hit/miss results",
    ["tenant_id", "tier", "result"],
)

master_orchestrator_workflow_duration_seconds = _get_or_create_histogram(
    "sanskritisetu_master_orchestrator_workflow_duration_seconds",
    "MasterOrchestratorAgent.process_task() duration by outcome",
    ["tenant_id", "status"],
)

# ==================== END AgentRouterAgent / MasterOrchestratorAgent Metrics ====================


# Regex patterns for dynamic path segments
_UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_ID_PATTERN = re.compile(r"^\d+$|^\d+[a-zA-Z0-9_-]*$|^[a-fA-F0-9]{8,}$")


def _normalize_path(path: str) -> str:
    """
    Normalize a URL path by replacing dynamic segments with placeholders.

    This prevents high Prometheus cardinality from IDs, UUIDs, and other
    variable path segments.

    Examples:
        /api/v1/users/123          -> /api/v1/users/{id}
        /api/v1/agents/<uuid>      -> /api/v1/agents/{id}
        /api/v1/health             -> /api/v1/health
    """
    if not path or path == "/":
        return path

    segments = path.split("/")
    normalized: list[str] = []
    for segment in segments:
        if not segment:
            normalized.append(segment)
            continue
        # Skip API version segments like "v1", "v2"
        if re.match(r"^v\d+$", segment):
            normalized.append(segment)
            continue
        if _UUID_PATTERN.match(segment) or _ID_PATTERN.match(segment):
            normalized.append("{id}")
        else:
            normalized.append(segment)

    return "/".join(normalized)


class PrometheusMiddleware:
    """
    Middleware to track Prometheus metrics for every request.
    Captures method, endpoint, status code, and tenant_id.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        method = scope["method"]
        path = _normalize_path(scope["path"])

        # Default status code (will be updated by send wrapper)
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.time() - start_time
            tenant_id = get_tenant_id() or "system"

            # Record metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=path,
                status_code=status_code,
                tenant_id=tenant_id,
            ).inc()

            REQUEST_LATENCY.labels(method=method, endpoint=path, tenant_id=tenant_id).observe(
                duration
            )

            # Track errors (status code >= 400)
            if status_code >= 400:
                HTTP_ERRORS_TOTAL.labels(
                    method=method, endpoint=path, status_code=status_code
                ).inc()
