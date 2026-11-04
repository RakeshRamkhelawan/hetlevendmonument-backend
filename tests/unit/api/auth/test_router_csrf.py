"""Unit tests for CSRF token endpoint (src.core.api.auth.router_csrf)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from fastapi.routing import APIRoute

from src.core.api.auth.dependencies import CSRF_TOKEN_EXPIRY, CSRF_TOKEN_PREFIX
from src.core.api.auth.router_csrf import get_csrf_token, router


def test_csrf_router_configuration() -> None:
    """Verify router has tags and route registered."""
    assert "Authentication" in router.tags
    route_paths = [r.path for r in router.routes if isinstance(r, APIRoute)]
    assert "/csrf-token" in route_paths



@pytest.mark.unit
async def test_get_csrf_token_success() -> None:
    """Verify happy path: token generated, stored in Redis with prefix and returned."""
    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.100"
    mock_request.headers.get.return_value = "Mozilla/5.0 TestBrowser"

    mock_redis = AsyncMock()

    with patch("src.core.api.auth.router_csrf.get_redis_client", return_value=mock_redis):
        result = await get_csrf_token(request=mock_request)

    assert "csrf_token" in result
    assert "expires_in" in result
    assert result["expires_in"] == CSRF_TOKEN_EXPIRY

    token = result["csrf_token"]
    assert isinstance(token, str)
    assert len(token) > 20

    # Verify Redis storage contract
    mock_redis.setex.assert_awaited_once()
    call_args = mock_redis.setex.await_args[0]
    session_key, expiry, stored_token = call_args

    assert session_key.startswith(CSRF_TOKEN_PREFIX)
    assert "192.168.1.100" in session_key
    assert "Mozilla/5.0" in session_key
    assert expiry == CSRF_TOKEN_EXPIRY
    assert stored_token == token


@pytest.mark.unit
async def test_get_csrf_token_fallback_when_client_or_header_missing() -> None:
    """Verify fallback to 'unknown' when client.host or user-agent is absent."""
    mock_request = MagicMock()
    mock_request.client = None
    mock_request.headers.get.return_value = "unknown"

    mock_redis = AsyncMock()

    with patch("src.core.api.auth.router_csrf.get_redis_client", return_value=mock_redis):
        result = await get_csrf_token(request=mock_request)

    assert "csrf_token" in result
    mock_redis.setex.assert_awaited_once()
    session_key = mock_redis.setex.await_args[0][0]
    assert "unknown:unknown" in session_key


@pytest.mark.unit
async def test_get_csrf_token_raises_500_on_redis_error() -> None:
    """Verify error path: Redis failure raises 500 HTTPException."""
    mock_request = MagicMock()
    mock_request.client.host = "10.0.0.1"
    mock_request.headers.get.return_value = "agent"

    mock_redis = AsyncMock()
    mock_redis.setex.side_effect = ConnectionError("Redis down")

    with patch("src.core.api.auth.router_csrf.get_redis_client", return_value=mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await get_csrf_token(request=mock_request)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to generate CSRF token"
