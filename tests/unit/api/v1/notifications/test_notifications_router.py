"""
Unit tests for notifications router (src/core/api/v1/notifications/router.py).

Covers:
- GET /notifications
- POST /notifications/mark-all-read
- POST /notifications/{notification_id}/read
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.v1.notifications.dependencies import get_notifications_service
from src.core.api.v1.notifications.router import router


@pytest.fixture
def sample_notification():
    return {
        "id": 1,
        "tenant_id": 1,
        "user_id": 10,
        "type": "alert",
        "title": "New Alert",
        "body": "System update completed",
        "data": {},
        "channel": "in_app",
        "is_read": False,
        "read_at": None,
        "created_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def mock_service(sample_notification):
    svc = AsyncMock()
    svc.list_notifications.return_value = {
        "items": [sample_notification],
        "total": 1,
    }
    svc.mark_all_read.return_value = 5
    read_notif = dict(sample_notification)
    read_notif["is_read"] = True
    read_notif["read_at"] = datetime.now(timezone.utc)
    svc.mark_single_read.return_value = read_notif
    return svc


@pytest.fixture
def test_app(mock_service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_notifications_service] = lambda: mock_service
    return app


@pytest.mark.asyncio
async def test_list_notifications_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/notifications?limit=10&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 1
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == 1


@pytest.mark.asyncio
async def test_mark_all_read_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/notifications/mark-all-read")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["count"] == 5


@pytest.mark.asyncio
async def test_mark_as_read_success(test_app, mock_service):
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/notifications/1/read")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] == 1
        assert data["data"]["is_read"] is True


@pytest.mark.asyncio
async def test_mark_as_read_not_found(test_app, mock_service):
    mock_service.mark_single_read.return_value = None
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.post("/notifications/999/read")
        assert response.status_code == 404
        assert "Notification not found" in response.json()["detail"]
