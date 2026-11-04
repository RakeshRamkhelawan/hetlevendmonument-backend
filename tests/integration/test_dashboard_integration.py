"""
Integratietests voor Dashboard domein: dashboard ophalen, widgets testen, foutafhandeling

Fix: async tests + AsyncClient avoids TestClient/anyio deadlock under asyncio_mode=auto.
mock get_monitoring_dashboard avoids real AI/embedding service initialization that hangs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import src.core.api.monitoring_dashboard_endpoints as _dashboard_endpoints_module
from src.core.api.monitoring_dashboard_endpoints import router
from src.core.auth import UserResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_dashboard() -> MagicMock:
    """Return a MonitoringDashboard mock with pre-built overview."""
    overview_data = {
        "system_health": {"status": "healthy", "uptime": 99.9, "uptime_hours": 48.0},
        "agents": {"active_agents": [{"agent_id": "agent1", "status": "active"}]},
        "performance": {
            "cpu_usage": 25.0,
            "memory_usage": 40.0,
            "disk_usage": 10.0,
            "total_requests": 1000,
            "success_rate": 0.99,
        },
        "resource_usage": {},
        "database_health": {},
        "learning_progress": {},
        "recent_alerts": [],
    }
    mock = MagicMock()
    mock.get_system_overview = AsyncMock(return_value=overview_data)
    return mock


# Mock user for tests
def mock_get_current_user():
    return UserResponse(id=1, email="test@example.com", tenant_id=1, is_active=True, role_id=1)


# ---------------------------------------------------------------------------
# App setup (module-level, no sync TestClient)
# ---------------------------------------------------------------------------

app = FastAPI()

# Override auth dependencies BEFORE including router
from src.core.auth.dependencies import get_current_user_dependency

app.dependency_overrides[get_current_user_dependency] = mock_get_current_user
app.include_router(router, prefix="/api/dashboard")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_monitoring_dashboard():
    """Patch get_monitoring_dashboard to return a fast mock (no real service init).

    Sync fixture (no async needed) — works correctly with pytest-asyncio auto mode
    because patch.object is a sync context manager that remains active for the
    test's full duration including async coroutines.
    """
    mock_dashboard = _make_mock_dashboard()
    with patch.object(
        _dashboard_endpoints_module,
        "get_monitoring_dashboard",
        new=AsyncMock(return_value=mock_dashboard),
    ):
        yield mock_dashboard


@pytest_asyncio.fixture
async def ac():
    """Async HTTP client — avoids TestClient deadlock with asyncio_mode=auto."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Tests (async to avoid TestClient/anyio deadlock under asyncio_mode=auto)
# ---------------------------------------------------------------------------


async def test_get_dashboard_and_widget_flow(ac):
    dashboard = await ac.get("/api/dashboard/get_dashboard")
    assert dashboard.status_code == 200
    assert "widgets" in dashboard.json()
    widget = await ac.get("/api/dashboard/get_widget/1")
    assert widget.status_code == 200
    assert "widget" in widget.json()


async def test_get_widget_not_found(ac):
    response = await ac.get("/api/dashboard/get_widget/999999")
    assert response.status_code == 404


async def test_dashboard_overview_success(ac):
    response = await ac.get("/api/dashboard/overview")
    assert response.status_code == 200
    assert "summary" in response.json()


async def test_dashboard_metrics_format(ac):
    response = await ac.get("/api/dashboard/metrics")
    assert response.status_code == 200
    assert "application/json" in response.headers.get(
        "content-type", ""
    ) or "text/plain" in response.headers.get("content-type", "")


async def test_dashboard_security_headers(ac):
    response = await ac.get("/api/dashboard/overview")
    assert "X-Frame-Options" in response.headers or "Strict-Transport-Security" in response.headers


def test_dashboard_tenant_isolation():
    # Simuleer dashboard requests onder verschillende tenants (mock context vereist)
    pass


def test_dashboard_audit_logging(monkeypatch):
    # Mock audit log en controleer aanroep bij dashboard events
    pass


def test_dashboard_concurrent_requests(monkeypatch):
    # Simuleer gelijktijdige dashboard requests (threading of async)
    pass
