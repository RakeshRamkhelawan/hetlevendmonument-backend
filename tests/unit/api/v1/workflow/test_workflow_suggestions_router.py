"""
Unit tests for workflow suggestions sub-router (src/core/api/v1/workflow/workflow_suggestions_router.py).

Covers:
- GET /api/v1/workflows/suggestions/{workflow_id}/suggestions
- GET /api/v1/workflows/suggestions/{workflow_id}/variants
"""

from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from src.core.api.v1.workflow.dependencies import get_db
from src.core.api.v1.workflow.workflow_suggestions_router import router, _get_tenant


@pytest.fixture
def mock_workflow():
    wf = MagicMock()
    wf.workflow_id = "wf_test_001"
    wf.name = "Test Workflow"
    wf.tenant_id = 1
    wf.is_active = True
    wf.spec_json = {
        "tasks": [
            {"ref": "start_step", "type": "task"},
            {"ref": "compute_step", "type": "task"},
            {"ref": "end_step", "type": "task"},
        ],
        "timeout": 3600,
    }
    return wf


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router)

    # Mock DB session and tenant
    mock_db = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[_get_tenant] = lambda: 1

    # Override any require_scopes dependency
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        for dep in dependant.dependencies if dependant else []:
            if getattr(dep.call, "__name__", "") == "scope_checker":
                app.dependency_overrides[dep.call] = lambda: 1

    return app


@pytest.mark.asyncio
async def test_get_workflow_suggestions_success(test_app, mock_workflow, monkeypatch):
    from src.core.api.v1.workflow import workflow_suggestions_router

    mock_get = AsyncMock(return_value=mock_workflow)
    monkeypatch.setattr(workflow_suggestions_router, "get_workflow_by_id", mock_get)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/workflows/suggestions/wf_test_001/suggestions")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf_test_001"
        assert "suggestions" in data
        assert isinstance(data["suggestions"], list)


@pytest.mark.asyncio
async def test_get_workflow_suggestions_with_filters(test_app, mock_workflow, monkeypatch):
    from src.core.api.v1.workflow import workflow_suggestions_router

    mock_get = AsyncMock(return_value=mock_workflow)
    monkeypatch.setattr(workflow_suggestions_router, "get_workflow_by_id", mock_get)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/workflows/suggestions/wf_test_001/suggestions?category=error&min_confidence=0.5&limit=5"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf_test_001"
        assert "suggestions" in data


@pytest.mark.asyncio
async def test_get_workflow_suggestions_not_found(test_app, monkeypatch):
    from src.core.api.v1.workflow import workflow_suggestions_router

    mock_get = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Workflow 'not_found' not found")
    )
    monkeypatch.setattr(workflow_suggestions_router, "get_workflow_by_id", mock_get)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/workflows/suggestions/not_found/suggestions")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_workflow_variants_success(test_app, mock_workflow, monkeypatch):
    from src.core.api.v1.workflow import workflow_suggestions_router

    mock_get = AsyncMock(return_value=mock_workflow)
    monkeypatch.setattr(workflow_suggestions_router, "get_workflow_by_id", mock_get)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/api/v1/workflows/suggestions/wf_test_001/variants")
        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == "wf_test_001"
        assert "baseline_metrics" in data
        assert "variants" in data
        assert len(data["variants"]) > 0


@pytest.mark.asyncio
async def test_get_workflow_variants_filtered(test_app, mock_workflow, monkeypatch):
    from src.core.api.v1.workflow import workflow_suggestions_router

    mock_get = AsyncMock(return_value=mock_workflow)
    monkeypatch.setattr(workflow_suggestions_router, "get_workflow_by_id", mock_get)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/workflows/suggestions/wf_test_001/variants?strategies=cost_optimized"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["variants"]) <= 1
