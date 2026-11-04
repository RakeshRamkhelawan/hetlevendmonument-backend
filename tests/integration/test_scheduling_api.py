"""Integration tests for the scheduling REST API.

Uses TestClient with a minimal FastAPI app that only includes the
scheduling router. Overrides get_current_user so every request is
authenticated as tenant_id=99, user_id=1.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.api.setup.exception_handlers import setup_exception_handlers
from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import Base, get_db
from src.core.models.rbac_models import Tenant  # noqa: F401
from src.core.scheduling.api.routes import router as scheduling_router


@pytest.fixture(autouse=True)
def _reset_scheduling_limiter():
    """Prevent inter-test rate-limit bleed from the module-level limiter."""
    from src.core.scheduling.api.routes import limiter as _limiter

    storage = getattr(_limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()


TENANT_ID = 99
USER_ID = 1


@pytest.fixture
def scheduling_client():
    """TestClient with minimal app, DB override, and auth override."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:sched_integ?mode=memory&cache=shared&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _close():
        await engine.dispose()

    async def override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    mock_user = UserResponse(
        id=USER_ID,
        email="test@sched.dev",
        tenant_id=TENANT_ID,
        roles=["admin"],
    )

    asyncio.run(_init())
    app: FastAPI = FastAPI(title="Scheduling Test")
    limiter = Limiter(key_func=get_remote_address, storage_uri="memory://", headers_enabled=True)
    app.state.limiter = limiter
    setup_exception_handlers(app)
    app.include_router(scheduling_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    client: TestClient = TestClient(app)
    yield client
    cast(FastAPI, client.app).dependency_overrides.clear()
    asyncio.run(_close())


# -------------------------------------------------------------------------
# Calendar event CRUD
# -------------------------------------------------------------------------


class TestCalendarEventEndpoints:
    """Tests for /api/v1/scheduling/events."""

    def _create_event(self, client, **overrides):
        now = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
        payload = {
            "title": overrides.get("title", "Test meeting"),
            "start_time": overrides.get("start_time", now.isoformat()),
            "end_time": overrides.get("end_time", (now + timedelta(hours=1)).isoformat()),
        }
        return client.post("/api/v1/scheduling/events", json=payload)

    def test_create_event_201(self, scheduling_client):
        resp = self._create_event(scheduling_client)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test meeting"
        assert data["id"] is not None
        assert data["tenant_id"] == TENANT_ID

    def test_get_event(self, scheduling_client):
        created = self._create_event(scheduling_client).json()
        resp = scheduling_client.get(f"/api/v1/scheduling/events/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Test meeting"

    def test_get_event_not_found(self, scheduling_client):
        resp = scheduling_client.get("/api/v1/scheduling/events/nonexistent-id")
        assert resp.status_code == 404

    def test_list_events(self, scheduling_client):
        self._create_event(scheduling_client, title="A")
        self._create_event(scheduling_client, title="B")
        resp = scheduling_client.get("/api/v1/scheduling/events")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_update_event(self, scheduling_client):
        created = self._create_event(scheduling_client).json()
        resp = scheduling_client.patch(
            f"/api/v1/scheduling/events/{created['id']}",
            json={"title": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"

    def test_update_event_not_found(self, scheduling_client):
        resp = scheduling_client.patch(
            "/api/v1/scheduling/events/nonexistent-id",
            json={"title": "X"},
        )
        assert resp.status_code == 404

    def test_cancel_event(self, scheduling_client):
        created = self._create_event(scheduling_client).json()
        resp = scheduling_client.delete(f"/api/v1/scheduling/events/{created['id']}")
        assert resp.status_code == 204
        # Should be gone now
        resp2 = scheduling_client.get(f"/api/v1/scheduling/events/{created['id']}")
        assert resp2.status_code == 404

    def test_cancel_event_not_found(self, scheduling_client):
        resp = scheduling_client.delete("/api/v1/scheduling/events/nonexistent-id")
        assert resp.status_code == 404


# -------------------------------------------------------------------------
# Time blocks
# -------------------------------------------------------------------------


class TestTimeBlockEndpoints:
    """Tests for /api/v1/scheduling/time-blocks."""

    def test_create_time_block_201(self, scheduling_client):
        now = datetime(2025, 7, 1, 14, 0, tzinfo=timezone.utc)
        resp = scheduling_client.post(
            "/api/v1/scheduling/time-blocks",
            json={
                "block_type": "focus_time",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
                "is_hard_block": True,
                "label": "Deep work",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["block_type"] == "focus_time"
        assert data["is_hard_block"] is True

    def test_list_time_blocks(self, scheduling_client):
        now = datetime(2025, 7, 1, 14, 0, tzinfo=timezone.utc)
        scheduling_client.post(
            "/api/v1/scheduling/time-blocks",
            json={
                "block_type": "break",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(minutes=30)).isoformat(),
            },
        )
        resp = scheduling_client.get("/api/v1/scheduling/time-blocks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_delete_time_block(self, scheduling_client):
        now = datetime(2025, 7, 1, 14, 0, tzinfo=timezone.utc)
        created = scheduling_client.post(
            "/api/v1/scheduling/time-blocks",
            json={
                "block_type": "focus_time",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        ).json()
        resp = scheduling_client.delete(f"/api/v1/scheduling/time-blocks/{created['id']}")
        assert resp.status_code == 204

    def test_delete_time_block_not_found(self, scheduling_client):
        resp = scheduling_client.delete("/api/v1/scheduling/time-blocks/nonexistent")
        assert resp.status_code == 404


# -------------------------------------------------------------------------
# Preferences
# -------------------------------------------------------------------------


class TestPreferenceEndpoints:
    """Tests for /api/v1/scheduling/preferences."""

    def test_get_preferences_none(self, scheduling_client):
        resp = scheduling_client.get("/api/v1/scheduling/preferences")
        assert resp.status_code == 200
        # No preferences set yet
        assert resp.json() is None

    def test_upsert_preferences(self, scheduling_client):
        resp = scheduling_client.put(
            "/api/v1/scheduling/preferences",
            json={
                "timezone_name": "Europe/Amsterdam",
                "working_hours_start": "09:00",
                "working_hours_end": "17:00",
                "preferred_duration_minutes": 45,
                "buffer_minutes": 10,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["timezone_name"] == "Europe/Amsterdam"
        assert data["buffer_minutes"] == 10

    def test_upsert_preferences_idempotent(self, scheduling_client):
        payload = {
            "timezone_name": "UTC",
            "working_hours_start": "08:00",
            "working_hours_end": "16:00",
        }
        scheduling_client.put("/api/v1/scheduling/preferences", json=payload)
        resp2 = scheduling_client.put(
            "/api/v1/scheduling/preferences",
            json={**payload, "buffer_minutes": 15},
        )
        assert resp2.status_code == 200
        assert resp2.json()["buffer_minutes"] == 15


def test_scheduling_routes_registered_in_integration_app(
    integration_app,
    scheduling_client,
):
    """Scheduling routes should be present in the production-style integration app."""
    paths = {route.path for route in integration_app.routes if hasattr(route, "path")}

    assert "/api/v1/scheduling/events" in paths
    assert "/api/v1/scheduling/preferences" in paths
    assert "/api/v1/scheduling/integrations" in paths

    # Use scheduling_client (isolated SQLite engine + mocked auth) to avoid the
    # session-scoped asyncpg engine being called from a function-scoped event loop.
    response = scheduling_client.get("/api/v1/scheduling/preferences")

    assert response.status_code == 200


# -------------------------------------------------------------------------
# Scheduling orchestration
# -------------------------------------------------------------------------


class TestScheduleMeetingEndpoint:
    """Tests for POST /api/v1/scheduling/schedule."""

    def test_schedule_meeting_success(self, scheduling_client):
        start = datetime(2025, 7, 2, 9, 0, tzinfo=timezone.utc)
        resp = scheduling_client.post(
            "/api/v1/scheduling/schedule",
            json={
                "title": "Sprint Review",
                "duration_minutes": 60,
                "participants": ["user-42"],
                "earliest_start": start.isoformat(),
                "latest_end": (start + timedelta(hours=8)).isoformat(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["event_id"] is not None
        assert data["message"] == "Meeting scheduled successfully."

    def test_schedule_meeting_no_window(self, scheduling_client):
        start = datetime(2025, 7, 2, 9, 0, tzinfo=timezone.utc)
        resp = scheduling_client.post(
            "/api/v1/scheduling/schedule",
            json={
                "title": "Impossible",
                "duration_minutes": 120,
                "participants": ["user-42"],
                "earliest_start": start.isoformat(),
                "latest_end": (start + timedelta(minutes=30)).isoformat(),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_schedule_meeting_validation_error(self, scheduling_client):
        """Missing required fields."""
        resp = scheduling_client.post(
            "/api/v1/scheduling/schedule",
            json={"title": "No participants"},
        )
        assert resp.status_code == 422


# -------------------------------------------------------------------------
# Tenant isolation
# -------------------------------------------------------------------------


class TestTenantIsolation:
    """Verify that events are scoped to the authenticated user's tenant."""

    def test_cannot_see_other_tenant_events(self, scheduling_client):
        # Create event as TENANT_ID=99
        now = datetime(2025, 7, 1, 10, 0, tzinfo=timezone.utc)
        created = scheduling_client.post(
            "/api/v1/scheduling/events",
            json={
                "title": "Tenant 99 event",
                "start_time": now.isoformat(),
                "end_time": (now + timedelta(hours=1)).isoformat(),
            },
        ).json()

        # Switch user to tenant 200
        other_user = UserResponse(id=2, email="other@test.dev", tenant_id=200, roles=["user"])
        scheduling_client.app.dependency_overrides[get_current_user] = lambda: other_user

        resp = scheduling_client.get(f"/api/v1/scheduling/events/{created['id']}")
        assert resp.status_code == 404
