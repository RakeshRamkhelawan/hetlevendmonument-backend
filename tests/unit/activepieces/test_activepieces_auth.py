"""Tests for ActivePieces endpoint authentication.

Verifies that all endpoints (except health checks) require authentication.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.activepieces_endpoints import router
from src.core.auth.dependencies import get_current_user


def _make_app() -> tuple[FastAPI, TestClient]:
    """Build a minimal FastAPI app with the ActivePieces router."""
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(router)

    # Override get_db so auth dependency can resolve without DB init
    db_mock = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db_mock

    from src.core.activepieces.service import get_activepieces_service

    mock_service = AsyncMock()
    mock_service.health_check.return_value = {"status": "ok"}
    mock_service.get_detailed_health.return_value = {"status": "ok", "latency": 1}
    app.dependency_overrides[get_activepieces_service] = lambda: mock_service

    return app, TestClient(app, raise_server_exceptions=False)


def _make_authed_app() -> tuple[FastAPI, TestClient]:
    """Build app with auth dependency overridden to a valid user."""
    from src.core.database.database import get_db

    app = FastAPI()
    app.include_router(router)

    user = MagicMock()
    user.id = 1
    user.tenant_id = 1
    user.email = "test@example.com"
    app.dependency_overrides[get_current_user] = lambda: user

    # Mock DB and service dependencies
    db_mock = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db_mock

    from src.core.activepieces.service import get_activepieces_service

    mock_service = AsyncMock()
    mock_service.get_all_pieces.return_value = []
    app.dependency_overrides[get_activepieces_service] = lambda: mock_service

    return app, TestClient(app)


class TestActivePiecesAuthRequired:
    """All ActivePieces endpoints (except health) must reject unauthenticated requests."""

    @pytest.fixture
    def client(self):
        app, client = _make_app()
        yield client

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/integrations/source-badges"),
            ("get", "/integrations/pieces/some-piece"),
            ("get", "/integrations/flows"),
            ("get", "/integrations/flows/flow-123"),
            ("post", "/integrations/flows"),
            ("put", "/integrations/flows/flow-123"),
            ("delete", "/integrations/flows/flow-123"),
            ("post", "/integrations/flows/flow-123/toggle"),
            ("post", "/integrations/flows/validate"),
            ("post", "/integrations/flows/flow-123/execute"),
            ("get", "/integrations/flows/flow-123/runs"),
            ("get", "/integrations/flows/flow-123/runs/run-456"),
            ("post", "/integrations/flows/flow-123/runs/run-456/retry"),
            ("post", "/integrations/flows/flow-123/runs/run-456/cancel"),
            ("get", "/integrations/connections"),
            ("get", "/integrations/connections/conn-123"),
            ("post", "/integrations/connections"),
            ("delete", "/integrations/connections/conn-123"),
            ("post", "/integrations/connections/conn-123/test"),
            ("put", "/integrations/connections/conn-123"),
        ],
    )
    def test_endpoint_rejects_unauthenticated(self, client, method, path):
        """Unauthenticated requests to protected endpoints receive 401."""
        response = client.request(method, path)
        assert (
            response.status_code == 401
        ), f"Expected 401 for {method.upper()} {path}, got {response.status_code}"

    @pytest.mark.parametrize(
        "method,path",
        [
            ("get", "/integrations/connections/oauth/slack/url?redirect_uri=http://localhost"),
            (
                "post",
                "/integrations/connections/oauth/callback?app_name=slack&code=abc&state=xyz&project_id=proj",
            ),
        ],
    )
    def test_oauth_endpoints_reject_unauthenticated(self, client, method, path):
        """OAuth endpoints reject unauthenticated requests (401 or 500 on misconfiguration)."""
        response = client.request(method, path)
        assert response.status_code in (
            401,
            500,
        ), f"Expected 401 or 500 for {method.upper()} {path}, got {response.status_code}"

    def test_health_endpoint_is_public(self, client):
        """Health check endpoints remain accessible without auth."""
        response = client.get("/integrations/health")
        # 503 is expected when ActivePieces is unconfigured; 401 would be wrong
        assert response.status_code != 401

    def test_health_detailed_endpoint_is_public(self, client):
        """Detailed health check remains accessible without auth."""
        response = client.get("/integrations/health/detailed")
        assert response.status_code != 401


class TestActivePiecesAuthSuccess:
    """Authenticated requests are accepted (auth dependency works)."""

    @pytest.fixture
    def client(self):
        app, client = _make_authed_app()
        yield client

    def test_source_badges_with_auth(self, client):
        """Authenticated request to source-badges succeeds."""
        response = client.get("/integrations/source-badges")
        assert response.status_code == 200
        assert response.json() == []
