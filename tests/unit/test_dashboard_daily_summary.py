# tests/unit/test_dashboard_daily_summary.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_db_session():
    session = MagicMock()
    session.execute = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = 5
    result_mock.scalars.return_value.all.return_value = []
    session.execute.return_value = result_mock
    return session


@pytest_asyncio.fixture
async def dashboard_client(mock_db_session):
    from src.core.api.v1.dashboard.router import router as dashboard_router
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(dashboard_router, prefix="/api/v1")

    async def override_get_current_user():
        from types import SimpleNamespace

        return SimpleNamespace(
            id=1, sub="1", user_id=1, tenant_id=1, email="test@example.com", roles=["user"]
        )

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_daily_summary_returns_200(dashboard_client):
    response = await dashboard_client.get(
        "/api/v1/dashboard/daily-summary",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.unit
async def test_daily_summary_returns_correct_shape(dashboard_client):
    response = await dashboard_client.get(
        "/api/v1/dashboard/daily-summary",
        headers={"Authorization": "Bearer test-token"},
    )
    data = response.json()
    assert data["success"] is True
    assert "tasksCompleted" in data["data"]
    assert "valueGenerated" in data["data"]
    assert "topAgent" in data["data"]
    assert "successRate" in data["data"]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_daily_summary_without_auth_returns_401(mock_db_session):
    from src.core.api.v1.dashboard.router import router as dashboard_router
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(dashboard_router, prefix="/api/v1")

    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/dashboard/daily-summary")

    assert response.status_code in (401, 403, 422)
    app.dependency_overrides.clear()
