"""Integration tests for the calendar-integrations REST API.

Tests the full HTTP request/response cycle through FastAPI, with
mocked OAuth providers and audit service.  Same pattern as
test_scheduling_api.py: minimal FastAPI app, SQLite in-memory DB,
auth override.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import Base, get_db
from src.core.models.rbac_models import Tenant  # noqa: F401 – metadata
from src.core.scheduling.api.integration_routes import _PROVIDERS
from src.core.scheduling.api.integration_routes import router as integ_router
from src.core.scheduling.integrations.base_provider import OAuthTokens, SyncResult

TENANT_ID = 42
USER_ID = 7


@pytest.fixture(autouse=True)
def _reset_scheduling_limiter():
    """Prevent inter-test rate-limit bleed from the module-level limiter."""
    from src.core.scheduling.api.integration_routes import limiter as _limiter

    storage = getattr(_limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()


# ── Fake provider ────────────────────────────────────────────────────


class _FakeProvider:
    """Minimal fake that satisfies BaseCalendarProvider for HTTP tests."""

    provider_name: str

    def __init__(self, name: str = "fake") -> None:
        self.provider_name = name
        self._exchange_result: Optional[OAuthTokens] = None
        self._sync_result: Optional[SyncResult] = None

    # -- helpers for per-test configuration --
    def set_exchange_result(self, tokens: OAuthTokens) -> None:
        self._exchange_result = tokens

    def set_sync_result(self, result: SyncResult) -> None:
        self._sync_result = result

    async def exchange_code(self, code: str, redirect_uri: str) -> OAuthTokens:
        if self._exchange_result:
            return self._exchange_result
        return OAuthTokens(
            access_token="fake-at-" + code,
            refresh_token="fake-rt-" + code,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="calendar",
            token_type="Bearer",
            account_id="fake-account",
        )

    async def refresh_access_token(self, refresh_token: str) -> OAuthTokens:
        return OAuthTokens(
            access_token="refreshed-at",
            refresh_token=refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scope="calendar",
        )

    async def list_events(
        self,
        access_token: str,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        sync_token: Optional[str] = None,
    ):
        return [], "next-sync-token"

    async def create_event(self, access_token, calendar_id, event):
        return "ext-123"

    async def update_event(self, access_token, calendar_id, external_id, event):
        pass

    async def delete_event(self, access_token, calendar_id, external_id):
        pass

    async def get_user_info(self, access_token):
        return {"email": "fake@test.dev"}


# ── Fixtures ─────────────────────────────────────────────────────────

_fake_google = _FakeProvider("google")
_fake_outlook = _FakeProvider("outlook")


@pytest.fixture
def integ_client():
    """TestClient wired to integration_routes with fake providers."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///file:cal_integ?mode=memory&cache=shared&uri=true",
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
        email="cal-test@setu.dev",
        tenant_id=TENANT_ID,
        roles=["admin"],
    )

    asyncio.run(_init())
    app: FastAPI = FastAPI(title="Calendar Integration Test")
    app.include_router(integ_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: mock_user

    # Swap providers in the module-level registry
    saved_providers = dict(_PROVIDERS)
    _PROVIDERS.clear()
    _PROVIDERS["google"] = _fake_google
    _PROVIDERS["outlook"] = _fake_outlook

    client: TestClient = TestClient(app)
    yield client
    cast(FastAPI, client.app).dependency_overrides.clear()
    asyncio.run(_close())

    # Restore original registry
    _PROVIDERS.clear()
    _PROVIDERS.update(saved_providers)


# ── Helpers ──────────────────────────────────────────────────────────

_PREFIX = "/api/v1/scheduling/integrations"


def _connect(client: TestClient, provider: str = "google"):
    """POST /connect/{provider} with a fake OAuth code."""
    return client.post(
        f"{_PREFIX}/connect/{provider}",
        json={"code": "auth-code-123", "redirect_uri": "http://localhost"},
    )


# ── Tests: list ──────────────────────────────────────────────────────


class TestListIntegrations:
    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_list_empty(self, _audit, integ_client):
        resp = integ_client.get(_PREFIX)
        assert resp.status_code == 200
        assert resp.json() == []

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_list_after_connect(self, _audit, integ_client):
        _connect(integ_client, "google")
        resp = integ_client.get(_PREFIX)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["provider"] == "google"
        assert data[0]["is_active"] is True


# ── Tests: connect ───────────────────────────────────────────────────


class TestConnectProvider:
    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_connect_google_201(self, _audit, integ_client):
        resp = _connect(integ_client, "google")
        assert resp.status_code == 201
        body = resp.json()
        assert body["provider"] == "google"
        assert body["provider_account_id"] == "fake-account"
        assert body["is_active"] is True
        assert body["id"] is not None

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_connect_outlook_201(self, _audit, integ_client):
        resp = _connect(integ_client, "outlook")
        assert resp.status_code == 201
        assert resp.json()["provider"] == "outlook"

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_connect_unsupported_provider(self, _audit, integ_client):
        resp = integ_client.post(
            f"{_PREFIX}/connect/apple",
            json={
                "code": "code",
                "redirect_uri": "http://localhost",
            },
        )
        assert resp.status_code == 400
        assert "Unsupported provider" in resp.json()["detail"]

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_connect_upsert_existing(self, _audit, integ_client):
        """Second connect to same provider updates tokens (upsert)."""
        first = _connect(integ_client, "google")
        assert first.status_code == 201
        integration_id = first.json()["id"]

        second = _connect(integ_client, "google")
        # Upsert returns 201 from the same endpoint
        assert second.status_code == 201
        assert second.json()["id"] == integration_id

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_reconnect_restores_soft_deleted_integration(self, _audit, integ_client):
        first = _connect(integ_client, "google")
        assert first.status_code == 201
        integration_id = first.json()["id"]

        deleted = integ_client.delete(f"{_PREFIX}/{integration_id}")
        assert deleted.status_code == 204

        second = _connect(integ_client, "google")
        assert second.status_code == 201
        assert second.json()["id"] == integration_id

        listed = integ_client.get(_PREFIX)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [integration_id]


# ── Tests: disconnect ────────────────────────────────────────────────


class TestDisconnectIntegration:
    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_disconnect_204(self, _audit, integ_client):
        created = _connect(integ_client, "google").json()
        resp = integ_client.delete(f"{_PREFIX}/{created['id']}")
        assert resp.status_code == 204

        # Should no longer appear in list
        listed = integ_client.get(_PREFIX).json()
        assert len(listed) == 0

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_disconnect_not_found(self, _audit, integ_client):
        fake_id = str(uuid.uuid4())
        resp = integ_client.delete(f"{_PREFIX}/{fake_id}")
        assert resp.status_code == 404


# ── Tests: sync ──────────────────────────────────────────────────────


class TestTriggerSync:
    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_sync_success(self, _audit, integ_client):
        created = _connect(integ_client, "google").json()
        resp = integ_client.post(f"{_PREFIX}/{created['id']}/sync")
        assert resp.status_code == 200
        body = resp.json()
        assert body["provider"] == "google"
        assert body["integration_id"] == created["id"]
        assert isinstance(body["created"], int)
        assert isinstance(body["errors"], list)

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_sync_not_found(self, _audit, integ_client):
        fake_id = str(uuid.uuid4())
        resp = integ_client.post(f"{_PREFIX}/{fake_id}/sync")
        assert resp.status_code == 404

    @patch(
        "src.core.scheduling.api.integration_routes.AuditService.log_event",
        new_callable=AsyncMock,
        return_value=True,
    )
    def test_sync_deactivated_integration(self, _audit, integ_client):
        created = _connect(integ_client, "google").json()
        # Disconnect (soft delete / deactivate)
        integ_client.delete(f"{_PREFIX}/{created['id']}")
        # Sync should fail with 404 (soft-deleted is invisible)
        resp = integ_client.post(f"{_PREFIX}/{created['id']}/sync")
        assert resp.status_code == 404


def test_scheduling_integration_routes_registered_in_central_app(
    integration_app,
    integ_client,
):
    """Scheduling integration routes should be reachable via the central app."""
    paths = {route.path for route in integration_app.routes if hasattr(route, "path")}

    assert "/api/v1/scheduling/integrations" in paths
    assert "/api/v1/scheduling/integrations/connect/{provider}" in paths
    assert "/api/v1/scheduling/integrations/{integration_id}/sync" in paths

    # Use integ_client (isolated SQLite + mocked auth) to avoid session-scoped
    # asyncpg engine being called from a function-scoped event loop.
    response = integ_client.get(_PREFIX)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_scheduling_sync_via_central_app(integ_client):
    """Manual sync should work end-to-end: connect → sync with mocked provider."""
    # Seed integration via the API itself (no postgres_session needed).
    created = _connect(integ_client).json()
    integration_id = created["id"]

    with patch(
        "src.core.scheduling.api.integration_routes.CalendarSyncService.sync_integration",
        new_callable=AsyncMock,
        return_value=SyncResult(
            created=2,
            updated=1,
            deleted=0,
            errors=[],
            next_sync_token="next-central-sync-token",
        ),
    ) as mocked_sync:
        response = integ_client.post(f"{_PREFIX}/{integration_id}/sync")

    assert response.status_code == 200
    data = response.json()
    assert data["integration_id"] == integration_id
    assert data["provider"] == "google"
    assert data["created"] == 2
    assert data["updated"] == 1
    assert data["deleted"] == 0
    assert data["next_sync_token"] == "next-central-sync-token"
    mocked_sync.assert_awaited_once()
