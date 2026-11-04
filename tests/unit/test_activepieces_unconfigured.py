"""
Integration test: ActivePieces returns empty array when unconfigured.

Verifies that GET /api/v1/integrations/source-badges returns 200 with []
when ActivePieces credentials are missing, instead of HTTP 500.

This test uses a minimal FastAPI app with the ActivePieces router.
It does NOT use sys.modules cache clearing (forbidden per DECISION_LOG).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.activepieces.service import (
    ActivePiecesService,
    _DisabledActivePiecesClient,
)
from src.core.api.activepieces_endpoints import router
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db


def _make_mock_user():
    """Create a mock authenticated user for dependency override."""
    user = MagicMock()
    user.id = 1
    user.tenant_id = 1
    user.email = "test@example.com"
    return user


@pytest.fixture
def client_with_disabled_ap():
    """Provide a TestClient where ActivePieces is disabled."""
    app = FastAPI()
    app.include_router(router)

    # Override auth dependency
    app.dependency_overrides[get_current_user] = _make_mock_user

    # Override DB dependency
    db_mock = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db_mock

    with TestClient(app) as client:
        yield client


@pytest.mark.unit
def test_source_badges_returns_empty_when_unconfigured(client_with_disabled_ap):
    """When ActivePieces is not configured, source-badges should return []."""
    # Geen tenant-verbinding (hier: geen pilot-tenant ingesteld) geeft de service de
    # _DisabledActivePiecesClient; de patch hieronder is een extra zekerheid dat de service zelf
    # geen client bouwt.
    with patch(
        "src.core.activepieces.service.ActivePiecesClient.__init__",
        side_effect=ValueError("ActivePieces not configured"),
    ):
        response = client_with_disabled_ap.get("/integrations/source-badges")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.unit
def test_source_badges_rejects_unauthenticated():
    """Unauthenticated requests to source-badges receive 401."""
    app = FastAPI()
    app.include_router(router)

    # Only override DB, not auth — so the normal auth check fires
    db_mock = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db_mock

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/integrations/source-badges")

    assert response.status_code == 401
