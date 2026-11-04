"""
Unit tests for audit missions sub-router (src/core/api/v1/audit/missions_router.py).

Covers:
- GET /missions (list missions with audit data)
- GET /missions/{mission_id}/export (GDPR export JSON, CSV, PDF, 404)
"""

from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.dependencies import get_db
from src.core.api.v1.audit.dependencies import get_tenant
from src.core.api.v1.audit.missions_router import router


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router)

    # Mock DB session and tenant
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_tenant] = lambda: 1

    # Override any require_scopes dependency
    for route in app.routes:
        for dep in getattr(route, "dependant", None) and route.dependant.dependencies or []:
            if getattr(dep.call, "__name__", "") == "scope_checker":
                app.dependency_overrides[dep.call] = lambda: {"user_id": "test_user", "email": "test@example.com"}

    return app


@pytest.mark.asyncio
async def test_list_missions_audit_success(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/missions?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert "missions" in data
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["missions"]) <= 2
        assert "total" in data


@pytest.mark.asyncio
async def test_list_missions_audit_with_filter(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/missions?status_filter=completed")
        assert response.status_code == 200
        data = response.json()
        assert "missions" in data


@pytest.mark.asyncio
async def test_export_mission_audit_json_success(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/missions/mission_001/export?format=json")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["mission"]["mission_id"] == "mission_001"
        assert "metadata" in data


@pytest.mark.asyncio
async def test_export_mission_audit_csv_success(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/missions/mission_001/export?format=csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert len(response.text) > 0


@pytest.mark.asyncio
async def test_export_mission_audit_pdf_simulated(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/missions/mission_001/export?format=pdf")
        assert response.status_code == 200
        assert response.headers.get("x-export-format") == "pdf-simulated"
        data = response.json()
        assert data["mission_id"] == "mission_001"


@pytest.mark.asyncio
async def test_export_mission_audit_not_found(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/missions/nonexistent_mission_id/export")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
