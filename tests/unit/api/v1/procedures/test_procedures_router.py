"""
Unit tests for procedures router (src/core/api/v1/procedures/router.py).

Covers:
- GET /procedures/
- GET /procedures/{procedure_id}
- POST /procedures/{procedure_id}/execute
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.v1.procedures.router import router
from src.core.auth.api_deps import get_current_user


@pytest.fixture
def test_app():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "tenant_id": 1}
    return app


@pytest.mark.asyncio
async def test_list_procedures_success(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/procedures/")
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] == 0
        assert data["page"] == 1


@pytest.mark.asyncio
async def test_get_procedure_not_found(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/procedures/42")
        assert response.status_code == 404
        assert "Procedure 42 not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_execute_procedure_not_found(test_app):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/procedures/42/execute", json={"parameters": {}})
        assert response.status_code == 404
        assert "Procedure 42 not found" in response.json()["detail"]
