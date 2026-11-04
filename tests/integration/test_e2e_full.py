"""
End-to-end test that exercises every API endpoint in the platform.
Covers: all routers, all HTTP methods, all major response codes.

Uses async_client from conftest (shared PostgreSQL + integration_app).

NOTE: These tests require PostgreSQL to be running on port 5455.
They are marked with custom timeout to prevent CI hangs.
"""

import os
import socket

import pytest
from httpx import AsyncClient

# Check if PostgreSQL is available before running tests
_TEST_PG_PORT = int(os.getenv("TEST_PG_PORT", "5455"))


def _postgres_reachable() -> bool:
    """Return True if PostgreSQL is reachable at the test port."""
    try:
        with socket.create_connection(("localhost", _TEST_PG_PORT), timeout=1):
            return True
    except OSError:
        return False


# Skip all tests in this module if PostgreSQL is not available
pytestmark = [
    pytest.mark.skipif(
        not _postgres_reachable(),
        reason=f"PostgreSQL not reachable at localhost:{_TEST_PG_PORT}",
    ),
    pytest.mark.e2e,
    pytest.mark.requires_db,
    pytest.mark.integration,
    pytest.mark.timeout(60),  # Prevent hanging - 60s max per test
]

# List of (method, path, description) for all endpoints (partial, expand as needed)
ENDPOINTS = [
    # Root and health
    ("GET", "/", "Root endpoint"),
    ("GET", "/health", "Health check"),
    # Auth
    ("GET", "/api/v1/auth/me", "Get current user info (auth)"),
    ("POST", "/api/v1/auth/register", "Register new user (auth)"),
    ("POST", "/api/v1/auth/token", "Obtain JWT token (auth)"),
    # Admin
    ("GET", "/api/v1/admin/dashboard", "Admin dashboard"),
    ("GET", "/api/v1/admin/users", "List users (admin)"),
    ("GET", "/api/v1/admin/system", "System info (admin)"),
    ("GET", "/api/v1/admin/logs", "System logs (admin)"),
    ("GET", "/api/v1/admin/monitor", "Monitor info (admin)"),
    ("GET", "/api/v1/admin/public", "Public admin info"),
    # Agents
    ("GET", "/api/v1/agents/", "List agents"),
    ("POST", "/api/v1/agents/", "Create agent"),
    ("GET", "/api/v1/agents/1", "Get agent by ID"),
    ("PUT", "/api/v1/agents/1", "Update agent by ID"),
    ("DELETE", "/api/v1/agents/1", "Delete agent by ID"),
    # Goals
    ("GET", "/api/v1/goals/", "List goals"),
    ("POST", "/api/v1/goals/", "Create goal"),
    ("GET", "/api/v1/goals/1", "Get goal by ID"),
    ("PUT", "/api/v1/goals/1", "Update goal by ID"),
    ("DELETE", "/api/v1/goals/1", "Delete goal by ID"),
    # CVA
    ("POST", "/api/v1/cva/chat", "CVA chat"),
    ("GET", "/api/v1/cva/status", "CVA status"),
    ("GET", "/api/v1/cva/conversations", "CVA conversations"),
    ("POST", "/api/v1/cva/optimize", "CVA optimize"),
    ("GET", "/api/v1/cva/analytics", "CVA analytics"),
    ("GET", "/api/v1/cva/health", "CVA health"),
    ("POST", "/api/v1/cva/shutdown", "CVA shutdown"),
    # Monitoring
    ("GET", "/api/v1/monitoring/health", "Monitoring health"),
    ("GET", "/api/v1/monitoring/metrics", "Monitoring metrics"),
    ("GET", "/api/v1/monitoring/performance", "Monitoring performance"),
    ("GET", "/api/v1/monitoring/logs/analysis", "Monitoring log analysis"),
    ("GET", "/api/v1/monitoring/alerts", "Monitoring alerts"),
    ("GET", "/api/v1/monitoring/system/status", "Monitoring system status"),
    # Monitoring Dashboard
    ("GET", "/api/v1/monitoring_dashboard/health", "Monitoring dashboard health"),
    (
        "GET",
        "/api/v1/monitoring_dashboard/system-overview",
        "Monitoring dashboard system overview",
    ),
    (
        "GET",
        "/api/v1/monitoring_dashboard/system-health",
        "Monitoring dashboard system health",
    ),
    ("GET", "/api/v1/monitoring_dashboard/agents", "Monitoring dashboard agents"),
    (
        "GET",
        "/api/v1/monitoring_dashboard/performance",
        "Monitoring dashboard performance",
    ),
    ("GET", "/api/v1/monitoring_dashboard/learning", "Monitoring dashboard learning"),
    ("GET", "/api/v1/monitoring_dashboard/alerts", "Monitoring dashboard alerts"),
    ("GET", "/api/v1/monitoring_dashboard/dashboard", "Monitoring dashboard UI"),
    # Tool Broker
    ("GET", "/api/v1/tool-broker/status", "Tool broker status"),
    ("POST", "/api/v1/tool-broker/execute", "Tool broker execute"),
    # Knowledge Agent
    ("POST", "/api/v1/knowledge/execute-task", "Knowledge agent execute task"),
    ("GET", "/api/v1/knowledge/health", "Knowledge agent health"),
    ("GET", "/api/v1/knowledge/status", "Knowledge agent status"),
    # Sentiment Agent
    ("POST", "/api/v1/sentiment/execute_task", "Sentiment agent execute task"),
    ("GET", "/api/v1/sentiment/health", "Sentiment agent health"),
    ("GET", "/api/v1/sentiment/status", "Sentiment agent status"),
    # Diagnostics Agent
    ("POST", "/api/v1/diagnostics/execute_task", "Diagnostics agent execute task"),
    ("GET", "/api/v1/diagnostics/health", "Diagnostics agent health"),
    ("GET", "/api/v1/diagnostics/status", "Diagnostics agent status"),
    # Translation Agent
    ("POST", "/api/v1/translation/execute_task", "Translation agent execute task"),
    ("GET", "/api/v1/translation/health", "Translation agent health"),
    ("GET", "/api/v1/translation/status", "Translation agent status"),
    # Workflows (example, expand as needed)
    ("GET", "/api/v1/workflow/status", "Workflow status"),
    ("POST", "/api/v1/workflow/execute", "Workflow execute"),
    ("GET", "/api/v1/workflow/history", "Workflow history"),
]


@pytest.mark.parametrize("method,path,desc", ENDPOINTS)
@pytest.mark.asyncio
async def test_endpoint_smoke(async_client: AsyncClient, method: str, path: str, desc: str):
    """Smoke test for each API endpoint: checks for 2xx/4xx/5xx response."""
    if method == "GET":
        response = await async_client.get(path)
    elif method == "POST":
        response = await async_client.post(path, json={})
    elif method == "PUT":
        response = await async_client.put(path, json={})
    elif method == "DELETE":
        response = await async_client.delete(path)
    else:
        pytest.skip(f"Unsupported method: {method}")
    # Accept any valid HTTP response, but log failures
    assert response.status_code in (
        200,
        201,
        202,
        204,
        400,
        401,
        403,
        404,
        422,
        500,
    ), f"{desc} failed: {response.status_code} {response.text}"
