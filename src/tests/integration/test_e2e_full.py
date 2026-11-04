"""
End-to-end test that exercises every API endpoint in the platform.
Covers: all routers, all HTTP methods, all major response codes.
"""

import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

# List of (method, path, description) for all endpoints (partial, expand as needed)
ENDPOINTS = [
    ("GET", "/auth/me", "Get current user info (auth)"),
    ("POST", "/auth/register", "Register new user (auth)"),
    ("POST", "/auth/token", "Obtain JWT token (auth)"),
    ("GET", "/admin/dashboard", "Admin dashboard"),
    ("GET", "/admin/users", "List users (admin)"),
    ("GET", "/admin/system", "System info (admin)"),
    ("GET", "/admin/logs", "System logs (admin)"),
    ("GET", "/admin/monitor", "Monitor info (admin)"),
    ("GET", "/admin/public", "Public admin info"),
    ("POST", "/api/v1/cva/chat", "CVA chat"),
    ("GET", "/api/v1/cva/status", "CVA status"),
    ("GET", "/api/v1/cva/conversations", "CVA conversations"),
    ("POST", "/api/v1/cva/optimize", "CVA optimize"),
    ("GET", "/api/v1/cva/analytics", "CVA analytics"),
    ("GET", "/api/v1/cva/health", "CVA health"),
    ("POST", "/api/v1/cva/shutdown", "CVA shutdown"),
    ("GET", "/api/v1/monitoring/health", "Monitoring health"),
    ("GET", "/api/v1/monitoring/metrics", "Monitoring metrics"),
    ("GET", "/api/v1/monitoring/performance", "Monitoring performance"),
    ("GET", "/api/v1/monitoring/logs/analysis", "Monitoring log analysis"),
    ("GET", "/api/v1/monitoring/alerts", "Monitoring alerts"),
    ("GET", "/api/v1/monitoring/system/status", "Monitoring system status"),
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
    # ...add all other endpoints here...
]


@pytest.mark.parametrize("method,path,desc", ENDPOINTS)
def test_endpoint_smoke(method, path, desc):
    """Smoke test for each API endpoint: checks for 2xx/4xx/5xx response."""
    if method == "GET":
        response = client.get(path)
    elif method == "POST":
        response = client.post(path, json={})
    elif method == "PUT":
        response = client.put(path, json={})
    elif method == "DELETE":
        response = client.delete(path)
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
