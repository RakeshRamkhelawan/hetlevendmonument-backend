"""
Tests for deprecation banner on POST /api/v1/intents/parse.

Verifies:
- Response includes Deprecation header
- Response includes Sunset header
- OpenAPI schema marks endpoint as deprecated
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.api.copilot_endpoints import router as intents_router


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    from src.core.database.database import get_db

    async def _mock_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_db] = _mock_db

    from src.core.auth.dependencies import get_current_user

    class FakeUser:
        id = 1
        tenant_id = 42

    app.dependency_overrides[get_current_user] = lambda: FakeUser()
    app.include_router(intents_router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.unit
def test_parse_intent_includes_deprecation_header(client: TestClient) -> None:
    """Deprecated endpoint must include Deprecation response header.

    Per Day 5 refactor: Deprecation is an RFC 8594 IMF-fixdate, not literal "true".
    """
    response = client.post(
        "/api/v1/intents/parse",
        json={"query": "create a workflow for donor churn"},
    )
    assert response.status_code == 200
    deprecation = response.headers.get("Deprecation")
    assert deprecation is not None
    # RFC 8594 IMF-fixdate ends with " GMT"
    assert deprecation.endswith("GMT")
    # And references a year
    assert "2026" in deprecation or "2027" in deprecation


@pytest.mark.unit
def test_parse_intent_includes_sunset_header(client: TestClient) -> None:
    """Deprecated endpoint must include Sunset response header."""
    response = client.post(
        "/api/v1/intents/parse",
        json={"query": "create a workflow for donor churn"},
    )
    assert response.status_code == 200
    assert "Sunset" in response.headers
    # Sunset date should be parseable
    assert "2026" in response.headers["Sunset"]


@pytest.mark.unit
def test_parse_intent_openapi_marked_deprecated(client: TestClient) -> None:
    """OpenAPI schema must mark /api/v1/intents/parse as deprecated."""
    openapi = client.app.openapi()
    path_item = openapi["paths"]["/api/v1/intents/parse"]["post"]
    assert path_item.get("deprecated") is True
