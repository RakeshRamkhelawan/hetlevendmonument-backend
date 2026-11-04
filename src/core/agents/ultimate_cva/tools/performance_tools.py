"""
Performance Monitoring Tools
Connects to Prometheus to provide system observability to the CVA Agent.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger("CVA.PerformanceTools")

PROMETHEUS_URL = "http://prometheus:9090"


async def query_prometheus(query: str, step: str = "15s") -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Execute a raw PromQL query against the internal Prometheus instance.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query})

            if response.status_code != 200:
                logger.warning(f"Prometheus query failed: {response.status_code} - {response.text}")
                return {
                    "status": "error",
                    "error": f"Prometheus returned {response.status_code}",
                }

            data = response.json()
            if data["status"] != "success":
                return {"status": "error", "error": data.get("error", "Unknown error")}

            return {"status": "success", "data": data["data"]}

    except httpx.ConnectError:
        return {
            "status": "error",
            "error": "Cannot connect to Prometheus. Is the observability stack running? (Try 'make up-obs')",
        }
    except Exception as e:
        logger.error(f"Prometheus connection error: {e}")
        return {"status": "error", "error": str(e)}


def _extract_scalar(result: dict[str, Any], default: float = 0.0) -> float:  # TODO(TYPE): replace Any with concrete type
    """Helper to extract single value from PromQL result."""
    try:
        if result.get("status") == "success" and result.get("data", {}).get("result"):
            # Result format: [{'metric': {}, 'value': [timestamp, 'value_string']}]
            val_str = result["data"]["result"][0]["value"][1]
            return float(val_str)
    except (KeyError, IndexError, ValueError):
        pass
    return default


async def get_system_metrics(window: str = "5m") -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Retrieves high-level system health metrics from Prometheus.
    Use this to "Check System Status".
    """
    # 1. Request Rate (Requests per second)
    rate_query = "rate(http_requests_total[5m])"  # Total across all instances
    # Sum it up
    total_rate = f"sum(rate(http_requests_total[{window}]))"

    # 2. Error Rate (5xx errors)
    error_rate = f'sum(rate(http_requests_total{{status=~"5.."}}[{window}])) / sum(rate(http_requests_total[{window}])) * 100'

    # 3. Backend Latency (P95)
    latency_query = f"histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[{window}])) by (le))"

    # 4. CPU Usage (Container - simplistic, assuming 'backend' container exists)
    # Note: 'container_cpu_usage_seconds_total' requires Cadvisor.
    # Fallback: process_cpu_seconds_total from the python process if exported
    cpu_query = f"rate(process_cpu_seconds_total[{window}]) * 100"

    # Execute queries in parallel (in a real implementation, gather)
    # For robust tool, we do sequential or gather.
    # We'll assume direct python-client metrics are available.

    results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    # Execute
    res_rate = await query_prometheus(total_rate)
    res_err = await query_prometheus(error_rate)
    res_lat = await query_prometheus(latency_query)
    res_cpu = await query_prometheus(cpu_query)

    # Check connectivity first
    if res_rate.get("status") == "error":
        return {
            "success": False,
            "message": res_rate.get("error", "Prometheus unreachable"),
            "data": {},
        }

    metrics = {
        "request_rate_ops": _extract_scalar(res_rate),
        "error_rate_percent": _extract_scalar(res_err),
        "p95_latency_seconds": _extract_scalar(res_lat),
        "cpu_usage_percent": _extract_scalar(res_cpu),
        "window": window,
        "source": "Prometheus",
    }

    return {
        "success": True,
        "metrics": metrics,
        "analysis_hint": "Latency > 1.0s is BAD. Error rate > 1% is CRITICAL.",
    }
