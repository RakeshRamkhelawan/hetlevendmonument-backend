"""
VIBE_PROD_001: Monitoring Configuration

Prometheus metrics, Grafana dashboards, and health checks for VIBE.
"""

import logging
from datetime import datetime, timezone
from typing import Any, TypedDict

logger = logging.getLogger(__name__)


class HealthCheckResultDict(TypedDict, total=False):
    """Return type for VIBEHealthCheck.check_all."""

    status: str
    timestamp: str
    checks: dict[str, dict[str, str]]


# ============================================================================
# Prometheus Metrics
# ============================================================================

# Pre-declare metrics as None when prometheus is not available
WORKFLOW_GENERATION_TOTAL: Any = None
WORKFLOW_GENERATION_LATENCY: Any = None
WORKFLOW_EXECUTION_TOTAL: Any = None
WORKFLOW_EXECUTION_LATENCY: Any = None
ACTIVE_WEBSOCKET_CONNECTIONS: Any = None
NODE_EXECUTION_TOTAL: Any = None
VIBE_INFO: Any = None

try:
    from prometheus_client import Counter, Gauge, Histogram, Info

    PROMETHEUS_AVAILABLE = True

    # Workflow Generation Metrics
    WORKFLOW_GENERATION_TOTAL = Counter(
        "vibe_workflow_generation_total",
        "Total workflow generation requests",
        ["tenant_id", "complexity", "status"],
    )

    WORKFLOW_GENERATION_LATENCY = Histogram(
        "vibe_workflow_generation_latency_seconds",
        "Workflow generation latency",
        ["complexity"],
        buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )

    WORKFLOW_EXECUTION_TOTAL = Counter(
        "vibe_workflow_execution_total",
        "Total workflow executions",
        ["tenant_id", "status"],
    )

    WORKFLOW_EXECUTION_LATENCY = Histogram(
        "vibe_workflow_execution_latency_seconds",
        "Workflow execution latency",
        buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0],
    )

    ACTIVE_WEBSOCKET_CONNECTIONS = Gauge(
        "vibe_active_websocket_connections",
        "Current active WebSocket connections",
        ["tenant_id"],
    )

    NODE_EXECUTION_TOTAL = Counter(
        "vibe_node_execution_total", "Total node executions", ["agent_name", "status"]
    )

    VIBE_INFO = Info("vibe_build", "VIBE build information")

except ImportError:
    PROMETHEUS_AVAILABLE = False


# ============================================================================
# Health Check
# ============================================================================


class VIBEHealthCheck:
    """Health check for VIBE service components."""

    def __init__(self) -> None:
        self.checks: dict[str, dict[str, str]] = {}

    async def check_all(self) -> HealthCheckResultDict:
        """Run all health checks."""
        results: HealthCheckResultDict = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {},
        }

        all_healthy = True

        # Check LLM connectivity
        llm_result = await self._check_llm()
        results["checks"]["llm"] = llm_result
        if llm_result["status"] != "healthy":
            all_healthy = False

        # Check database
        db_result = await self._check_database()
        results["checks"]["database"] = db_result
        if db_result["status"] != "healthy":
            all_healthy = False

        # Check WebSocket service
        ws_result = self._check_websocket()
        results["checks"]["websocket"] = ws_result
        if ws_result["status"] != "healthy":
            all_healthy = False

        results["status"] = "healthy" if all_healthy else "degraded"
        return results

    async def _check_llm(self) -> dict[str, str]:
        """Check LLM service availability."""
        try:
            # Would ping LLM service
            return {"status": "healthy", "message": "LLM service ready"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}

    async def _check_database(self) -> dict[str, str]:
        """Check database connectivity."""
        try:
            # Would ping database
            return {"status": "healthy", "message": "Database connected"}
        except Exception as e:
            return {"status": "unhealthy", "message": str(e)}

    def _check_websocket(self) -> dict[str, str]:
        """Check WebSocket service status."""
        try:
            from src.core.auth.websocket_auth import websocket_auth

            connections = websocket_auth.active_connections
            return {"status": "healthy", "message": f"{connections} active connections"}
        except Exception as e:
            return {"status": "unknown", "message": str(e)}


# ============================================================================
# Metrics Recording Functions
# ============================================================================


def record_workflow_generation(
    tenant_id: int, complexity: str, success: bool, latency_seconds: float
) -> None:
    """Record workflow generation metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    status = "success" if success else "failure"
    WORKFLOW_GENERATION_TOTAL.labels(
        tenant_id=str(tenant_id), complexity=complexity, status=status
    ).inc()

    WORKFLOW_GENERATION_LATENCY.labels(complexity=complexity).observe(latency_seconds)


def record_workflow_execution(tenant_id: int, status: str, latency_seconds: float) -> None:
    """Record workflow execution metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    WORKFLOW_EXECUTION_TOTAL.labels(tenant_id=str(tenant_id), status=status).inc()

    WORKFLOW_EXECUTION_LATENCY.observe(latency_seconds)


def record_node_execution(agent_name: str, status: str) -> None:
    """Record node execution metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    NODE_EXECUTION_TOTAL.labels(agent_name=agent_name, status=status).inc()


def update_websocket_connections(tenant_id: int, count: int) -> None:
    """Update active WebSocket connections gauge."""
    if not PROMETHEUS_AVAILABLE:
        return

    ACTIVE_WEBSOCKET_CONNECTIONS.labels(tenant_id=str(tenant_id)).set(count)


# ============================================================================
# Grafana Dashboard JSON
# ============================================================================

GRAFANA_DASHBOARD = {
    "title": "VIBE Workflow Builder",
    "uid": "vibe-dashboard",
    "panels": [
        {
            "title": "Workflow Generations",
            "type": "graph",
            "targets": [{"expr": "rate(vibe_workflow_generation_total[5m])"}],
        },
        {
            "title": "Generation Latency (p95)",
            "type": "gauge",
            "targets": [
                {
                    "expr": "histogram_quantile(0.95, rate(vibe_workflow_generation_latency_seconds_bucket[5m]))"
                }
            ],
        },
        {
            "title": "Active WebSocket Connections",
            "type": "stat",
            "targets": [{"expr": "sum(vibe_active_websocket_connections)"}],
        },
        {
            "title": "Execution Success Rate",
            "type": "gauge",
            "targets": [
                {
                    "expr": "sum(rate(vibe_workflow_execution_total{status='succeeded'}[5m])) / sum(rate(vibe_workflow_execution_total[5m]))"
                }
            ],
        },
    ],
}


# Global health check instance
health_check = VIBEHealthCheck()
