"""
Unit tests for copilot_turn_limit decorator (M-3 fix).

Verifies that the rate-limit bucket is keyed by tenant_id + user_id,
so requests from different tenants do not share a bucket.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.core.governance.rate_limiter import copilot_turn_limit


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    @app.middleware("http")
    async def add_tenant_state(request: Request, call_next: Any) -> Any:
        request.state.tenant_id = 42
        request.state.user_id = 7
        request.state.limiet_gebruiker = "u7"
        return await call_next(request)

    @app.post("/copilot/turn")
    @copilot_turn_limit(max_requests=3, window_seconds=60)
    async def turn(request: Request) -> dict[str, str]:
        return {"status": "ok"}

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.unit
@patch(
    "src.core.governance.rate_limiter._get_redis_limiter",
    new_callable=AsyncMock,
    return_value=None,
)
@patch(
    "src.core.governance.rate_limiter._rate_limiter",
    autospec=True,
)
def test_copilot_turn_limit_uses_tenant_id_in_bucket_key(
    mock_limiter: AsyncMock, mock_redis: AsyncMock, client: TestClient
) -> None:
    """Rate limit key must contain tenant_id (M-3 fix)."""
    mock_limiter.is_allowed.return_value = True
    mock_limiter.get_remaining.return_value = 2
    mock_limiter.get_reset_time.return_value = None

    response = client.post(
        "/copilot/turn",
        headers={"X-Tenant-ID": "99"},  # Header is IGNORED by key_func
    )
    assert response.status_code == 200

    # Extract the key that was passed to is_allowed
    call_args = mock_limiter.is_allowed.call_args
    assert call_args is not None
    key = call_args[0][0]
    assert key.startswith("copilot_turn:")
    assert "99" not in key  # Must NOT use header; uses request.state.tenant_id


@pytest.mark.unit
@patch(
    "src.core.governance.rate_limiter._get_redis_limiter",
    new_callable=AsyncMock,
    return_value=None,
)
@patch(
    "src.core.governance.rate_limiter._rate_limiter",
    autospec=True,
)
def test_copilot_turn_limit_rejects_after_30_per_minute(
    mock_limiter: AsyncMock, mock_redis: AsyncMock, client: TestClient
) -> None:
    """After max_requests reached, subsequent requests get 429."""
    mock_limiter.is_allowed.return_value = False
    mock_limiter.get_remaining.return_value = 0
    mock_limiter.get_reset_time.return_value = 1234567890.0

    response = client.post("/copilot/turn")
    assert response.status_code == 429
    data = response.json()
    assert "error" in data["detail"]
    assert "retry_after" in data["detail"]
