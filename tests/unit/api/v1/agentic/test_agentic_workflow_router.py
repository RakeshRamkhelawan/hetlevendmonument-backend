"""
Unit tests for agentic workflow router (src/core/api/v1/agentic/workflow_router.py).

Covers:
- POST /workflow/start
- GET /workflow/{task_id}/status
- POST /workflow/{task_id}/step
- DELETE /workflow/{task_id}
"""

from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.v1.agentic.dependencies import get_agentic_orchestration_service
from src.core.api.v1.agentic.workflow_router import router


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.start_workflow.return_value = {"task_id": "task_123", "status": "dispatched"}
    svc.get_workflow_status.return_value = {"task_id": "task_123", "status": "running"}
    svc.advance_workflow_step.return_value = {"task_id": "task_123", "step": 2}
    svc.cancel_workflow.return_value = {"task_id": "task_123", "status": "cancelled"}
    return svc


@pytest.fixture
def test_app(mock_service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_agentic_orchestration_service] = lambda: mock_service
    return app


@pytest.mark.asyncio
async def test_start_workflow_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/workflow/start", json={"name": "test_wf", "steps": ["s1", "s2"]})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["task_id"] == "task_123"
        assert mock_service.start_workflow.called


@pytest.mark.asyncio
async def test_start_workflow_error_raises_502(test_app, mock_service):
    mock_service.start_workflow.side_effect = RuntimeError("Dispatch error")
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/workflow/start", json={"name": "test_wf"})
        assert response.status_code == 502
        assert "Workflow dispatch mislukt" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_workflow_status_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/workflow/task_123/status")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "running"


@pytest.mark.asyncio
async def test_advance_workflow_step_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/workflow/task_123/step")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["step"] == 2


@pytest.mark.asyncio
async def test_cancel_workflow_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.delete("/workflow/task_123")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["status"] == "cancelled"
