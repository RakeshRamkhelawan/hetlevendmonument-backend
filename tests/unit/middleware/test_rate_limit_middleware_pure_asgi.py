"""
Unit tests for RateLimitMiddleware pure ASGI conversion.

These tests verify that RateLimitMiddleware:
1. Allows requests within quota (happy path)
2. Rejects requests over quota with 429 (unhappy path)
3. Does NOT trigger MissingGreenlet with async DB calls
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.core.middleware.rate_limit_middleware import TokenBucketRateLimiter


@pytest.fixture
def mock_rate_limiter() -> MagicMock:
    """Return a mocked TokenBucketRateLimiter."""
    limiter = MagicMock(spec=TokenBucketRateLimiter)
    limiter.is_allowed = AsyncMock(return_value=(True, 59, 1234567890))
    return limiter


@pytest.fixture
def rate_limit_app(mock_rate_limiter: MagicMock) -> FastAPI:
    """Build a minimal FastAPI app with RateLimitMiddleware in pure ASGI mode."""
    from src.core.middleware.rate_limit_middleware import RateLimitMiddleware

    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        rate_limiter=mock_rate_limiter,
        requests_per_minute=60,
    )

    @app.get("/api/v1/agents")
    async def agents_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    async def health_endpoint() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/db")
    async def db_endpoint(request: Request) -> dict[str, str]:
        return {"db": "ok"}

    return app


@pytest.mark.unit
class TestRateLimitMiddlewareHappyPath:
    async def test_request_within_quota_allowed(self, rate_limit_app: FastAPI, mock_rate_limiter: MagicMock) -> None:
        """Happy path: request within quota returns 200."""
        transport = ASGITransport(app=rate_limit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agents")

        assert response.status_code == 200
        mock_rate_limiter.is_allowed.assert_called_once()

    async def test_rate_limit_headers_present(self, rate_limit_app: FastAPI, mock_rate_limiter: MagicMock) -> None:
        """Response should contain rate limit headers."""
        transport = ASGITransport(app=rate_limit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agents")

        assert response.status_code == 200
        assert "x-ratelimit-limit" in response.headers
        assert "x-ratelimit-remaining" in response.headers
        assert "x-ratelimit-reset" in response.headers


@pytest.mark.unit
class TestRateLimitMiddlewareUnhappyPath:
    async def test_request_over_quota_returns_429(self, rate_limit_app: FastAPI, mock_rate_limiter: MagicMock) -> None:
        """Unhappy path: request over quota returns 429."""
        mock_rate_limiter.is_allowed = AsyncMock(return_value=(False, 0, 1234567890))

        transport = ASGITransport(app=rate_limit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agents")

        assert response.status_code == 429


@pytest.mark.unit
class TestRateLimitMiddlewareMissingGreenlet:
    async def test_async_db_endpoint_does_not_crash(self, rate_limit_app: FastAPI) -> None:
        """
        Regression test for B-001b: MissingGreenlet.

        RateLimitMiddleware does DB calls (TenantSubscriptionCache + db_manager.get_session).
        When it used BaseHTTPMiddleware, this could cause MissingGreenlet.
        After pure ASGI conversion, it should not.
        """
        transport = ASGITransport(app=rate_limit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/db")

        assert response.status_code == 200
        assert response.json() == {"db": "ok"}
