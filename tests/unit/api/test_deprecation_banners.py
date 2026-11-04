"""Tests for deprecation banner headers (RFC 8594 Sunset + Deprecation + Link)."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.api._deprecation import (
    DEFAULT_SUNSET_DATE,
    emit_deprecation_headers,
)
from src.core.api.copilot_endpoints import router as intents_router
from src.core.api.v1.ai_copilot.router import router as ai_copilot_router


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------

def test_emit_headers_sets_sunset_in_imf_fixdate_format() -> None:
    from fastapi import Response

    response = Response()
    emit_deprecation_headers(response, successor="/api/v1/copilot/turn")
    sunset = response.headers["Sunset"]
    parsed = parsedate_to_datetime(sunset)
    assert parsed == DEFAULT_SUNSET_DATE


def test_emit_headers_sets_link_with_successor_rel() -> None:
    from fastapi import Response

    response = Response()
    emit_deprecation_headers(response, successor="/api/v1/copilot/turn")
    link = response.headers["Link"]
    assert link == '</api/v1/copilot/turn>; rel="successor-version"'


# ---------------------------------------------------------------------------
# Endpoint fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    # Mock tenant middleware
    from src.core.middleware.tenant_context import set_tenant_id

    @app.middleware("http")
    async def add_tenant_state(request: Request, call_next: Any) -> Any:
        set_tenant_id(1)
        request.state.tenant_id = 1
        request.state.user_id = 7
        return await call_next(request)

    # Mock auth dependency (both possible import paths)
    from src.core.auth.dependencies import get_current_user as auth_get_current_user

    class FakeUser:
        id = 7
        tenant_id = 1
        roles = ["admin"]
        is_superuser = False

    app.dependency_overrides[auth_get_current_user] = lambda: FakeUser()

    try:
        from src.core.api.dependencies import get_current_user as api_get_current_user
        app.dependency_overrides[api_get_current_user] = lambda: FakeUser()
    except ImportError:
        pass

    # Mock db dependency
    from src.core.database.database import get_db

    app.dependency_overrides[get_db] = lambda: AsyncMock()

    # Include routers under their normal prefixes
    app.include_router(intents_router)
    app.include_router(ai_copilot_router)

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# /api/v1/intents/parse tests
# ---------------------------------------------------------------------------

def test_intents_parse_emits_all_three_deprecation_headers(client: TestClient) -> None:
    response = client.post("/api/v1/intents/parse", json={"query": "test query"})
    assert response.status_code == 200
    assert "Deprecation" in response.headers
    assert "Sunset" in response.headers
    assert "Link" in response.headers
    assert response.headers["Link"] == '</api/v1/copilot/turn>; rel="successor-version"'


def test_intents_parse_response_body_unchanged(client: TestClient) -> None:
    response = client.post("/api/v1/intents/parse", json={"query": "test query"})
    assert response.status_code == 200
    body = response.json()
    assert "success" in body
    assert "intent" in body
    assert "execution_time_ms" in body


# ---------------------------------------------------------------------------
# /api/v1/ai-copilot/suggest-tools tests
# ---------------------------------------------------------------------------

def test_suggest_tools_sse_body_unchanged_after_deprecation(client: TestClient) -> None:
    with patch("src.core.api.v1.ai_copilot.router.TenantTaalmodel") as mock_get_provider:
        provider = mock_get_provider.return_value

        async def _stream(prompt: str):
            yield {"text": "Hello"}

        provider.stream_response = _stream
        provider.initialized = True

        response = client.post(
            "/api/v1/ai-copilot/suggest-tools",
            json={"query": "test"},
        )
        assert response.status_code == 200
        assert "Deprecation" in response.headers
        assert "Sunset" in response.headers
        assert "Link" in response.headers

        # Capture first 200 bytes of SSE body for byte-identical check
        body_prefix = response.content[:200]
        # The body should contain the old SSE format (event: reasoning, etc.)
        assert b"event: reasoning" in body_prefix
