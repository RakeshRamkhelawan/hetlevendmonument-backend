"""
Unit tests for agentic ROI router (src/core/api/v1/agentic/agentic_roi_router.py).

Covers:
- GET /roi/supervisor/{supervisor}
- GET /roi/dashboard
- GET /health
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.v1.agentic.agentic_roi_router import agentic_roi_router
from src.core.auth.api_deps import get_current_user


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(agentic_roi_router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "tenant_id": 1}
    return app


@pytest.mark.asyncio
async def test_health_check_success(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "agentic_api"


@pytest.mark.asyncio
async def test_get_supervisor_roi_success(test_app, monkeypatch):
    from src.core.api.v1.agentic import agentic_roi_router as router_mod

    monkeypatch.setattr(router_mod, "require_tenant_id", lambda: 1)

    mock_calc = MagicMock()
    mock_calc.calculate_supervisor_roi = AsyncMock(return_value={"roi": 2.5, "savings": 1000})
    monkeypatch.setattr(router_mod, "ROICalculator", lambda: mock_calc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/roi/supervisor/sup_001?hours=48")
        assert response.status_code == 200
        data = response.json()
        assert data["supervisor"] == "sup_001"
        assert data["hours"] == 48
        assert data["metrics"]["roi"] == 2.5


@pytest.mark.asyncio
async def test_get_supervisor_roi_not_found(test_app, monkeypatch):
    from src.core.api.v1.agentic import agentic_roi_router as router_mod

    monkeypatch.setattr(router_mod, "require_tenant_id", lambda: 1)

    mock_calc = MagicMock()
    mock_calc.calculate_supervisor_roi = AsyncMock(return_value=None)
    monkeypatch.setattr(router_mod, "ROICalculator", lambda: mock_calc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/roi/supervisor/unknown_sup")
        assert response.status_code == 404
        assert "No ROI data found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_roi_dashboard_success(test_app, monkeypatch):
    from src.core.api.v1.agentic import agentic_roi_router as router_mod

    monkeypatch.setattr(router_mod, "require_tenant_id", lambda: 1)

    mock_calc = MagicMock()
    mock_calc.get_dashboard_metrics = AsyncMock(return_value={"total_savings": 5000, "efficiency": 0.88})
    monkeypatch.setattr(router_mod, "ROICalculator", lambda: mock_calc)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/roi/dashboard?period=30d")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "30d"
        assert data["dashboard"]["total_savings"] == 5000
