# tests/unit/test_monetization_phase3_behavioral.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

from src.core.middleware.rate_limit_middleware import (
    RateLimitMiddleware,
    TokenBucketRateLimiter,
)
from src.core.security.feature_guard import RequireTier


async def _call_middleware(middleware, path="/api/v1/agents", headers=None):
    """Invoke ASGI middleware and capture response headers."""
    headers = headers or {}
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": b""}

    start_message = {}

    async def send(message):
        if message["type"] == "http.response.start":
            start_message.update(message)

    async def app(scope, receive, send):
        response = Response(content=b"ok")
        await response(scope, receive, send)

    middleware.app = app
    await middleware(scope, receive, send)
    return start_message


@pytest.mark.asyncio
@patch("src.core.middleware.rate_limit_middleware.TenantSubscriptionCache")
async def test_3_b_1_free_rate_limit_enforcement(mock_cache_class):
    """
    Test 3.B.1 (Free Rate Limit Enforcement):
    Verify that a tenant on free tier resolves a rate limit of 60 requests/min.
    """
    # Setup mock cache to return free tier
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value={"tier": "free", "status": "active"})
    mock_cache_class.return_value = mock_cache

    # Mock rate limiter
    mock_limiter = AsyncMock(spec=TokenBucketRateLimiter)
    mock_limiter.is_allowed = AsyncMock(return_value=(True, 59, 123456))

    middleware = RateLimitMiddleware(app=None, rate_limiter=mock_limiter, requests_per_minute=60)

    # Patch tenant extraction to simulate authenticated user
    with patch.object(middleware, "_extract_tenant_id_from_request", return_value=456):
        start_message = await _call_middleware(middleware)

    # Verify that is_allowed was called with limit=60
    mock_limiter.is_allowed.assert_awaited_once_with("user:456", 60)

    response_headers = {k.decode(): v.decode() for k, v in start_message.get("headers", [])}
    assert response_headers["x-ratelimit-limit"] == "60"


@pytest.mark.asyncio
@patch("src.core.middleware.rate_limit_middleware.TenantSubscriptionCache")
async def test_3_b_2_pro_rate_limit_expansion(mock_cache_class):
    """
    Test 3.B.2 (Pro Rate Limit Expansion):
    Verify that a tenant on pro tier resolves a rate limit of 360 requests/min.
    """
    # Setup mock cache to return pro tier
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value={"tier": "pro", "status": "active"})
    mock_cache_class.return_value = mock_cache

    # Mock rate limiter
    mock_limiter = AsyncMock(spec=TokenBucketRateLimiter)
    mock_limiter.is_allowed = AsyncMock(return_value=(True, 359, 123456))

    middleware = RateLimitMiddleware(app=None, rate_limiter=mock_limiter, requests_per_minute=60)

    # Patch tenant extraction to simulate authenticated user
    with patch.object(middleware, "_extract_tenant_id_from_request", return_value=456):
        start_message = await _call_middleware(middleware)

    # Verify that is_allowed was called with limit=360
    mock_limiter.is_allowed.assert_awaited_once_with("user:456", 360)

    response_headers = {k.decode(): v.decode() for k, v in start_message.get("headers", [])}
    assert response_headers["x-ratelimit-limit"] == "360"


@pytest.mark.unit
@patch("src.core.security.feature_guard.get_tenant_id")
@patch("src.core.security.feature_guard.TenantSubscriptionCache")
def test_3_b_3_feature_guard_rejection(mock_cache_class, mock_get_tenant_id):
    """
    Test 3.B.3 (Feature Guard Rejection):
    Verify that a tenant on starter tier gets 403 Forbidden on pro endpoint.
    """
    # Setup mock cache to return starter tier
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value={"tier": "starter", "status": "active"})
    mock_cache_class.return_value = mock_cache
    mock_get_tenant_id.return_value = 456

    app = FastAPI()

    @app.get("/pro-only-test")
    async def pro_only_endpoint(_: None = Depends(RequireTier("pro"))):
        return {"status": "ok"}

    client = TestClient(app)
    response = client.get("/pro-only-test")

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tier_insufficient"
    assert response.json()["detail"]["required_tier"] == "pro"
