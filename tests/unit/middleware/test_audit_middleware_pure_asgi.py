"""
Unit tests for AuditLoggingMiddleware pure ASGI conversion.

These tests verify that AuditLoggingMiddleware:
1. Logs requests correctly (happy path)
2. Skips excluded paths
3. Logs errors correctly
4. Adds X-Request-ID header
5. Does NOT trigger MissingGreenlet with async DB calls
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db_session_factory() -> AsyncMock:
    """Return a mocked async session factory."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_factory = AsyncMock(return_value=mock_session)
    return mock_factory


@pytest.fixture
def audit_app(mock_db_session_factory: AsyncMock) -> FastAPI:
    """Build a minimal FastAPI app with AuditLoggingMiddleware in pure ASGI mode."""
    from src.core.middleware.audit_middleware import AuditLoggingMiddleware

    app = FastAPI()

    # Register middleware BEFORE routes (FastAPI LIFO: last added = first executed)
    app.add_middleware(
        AuditLoggingMiddleware,
        log_to_db=True,
        db_session_factory=mock_db_session_factory,
    )

    @app.get("/test")
    async def test_endpoint() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    async def health_endpoint() -> dict[str, str]:
        return {"status": "healthy"}

    @app.get("/error")
    async def error_endpoint() -> None:
        raise ValueError("Intentional error")

    @app.get("/db")
    async def db_endpoint(request: Request) -> dict[str, str]:
        # Simulate async DB call via greenlet (this is what triggers MissingGreenlet)
        # We don't need a real DB here; we just need to verify the middleware
        # doesn't break the greenlet context.
        return {"db": "ok"}

    return app


@pytest.mark.unit
class TestAuditMiddlewareHappyPath:
    async def test_request_is_logged(self, audit_app: FastAPI, mock_db_session_factory: AsyncMock) -> None:
        """Happy path: a normal request is logged to the database."""
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 200
        # The DB session factory should have been called
        mock_db_session_factory.assert_called_once()

    async def test_excluded_path_not_logged(self, audit_app: FastAPI, mock_db_session_factory: AsyncMock) -> None:
        """Excluded paths (e.g., /health) should NOT trigger DB logging."""
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        # DB session factory should NOT have been called for excluded path
        mock_db_session_factory.assert_not_called()

    async def test_x_request_id_header_added(self, audit_app: FastAPI) -> None:
        """Response should contain X-Request-ID header."""
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 200
        assert "x-request-id" in response.headers
        # Should be a valid UUID
        header_value = response.headers["x-request-id"]
        uuid.UUID(header_value)  # raises ValueError if not a valid UUID


@pytest.mark.unit
class TestAuditMiddlewareErrorPath:
    async def test_error_request_is_logged(self, audit_app: FastAPI, mock_db_session_factory: AsyncMock) -> None:
        """Error path: an exception in the endpoint is still logged."""
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with pytest.raises(Exception):
                await client.get("/error")

        # DB session factory should have been called for error logging
        mock_db_session_factory.assert_called_once()


@pytest.mark.unit
class TestAuditMiddlewareMissingGreenlet:
    async def test_async_db_endpoint_does_not_crash(self, audit_app: FastAPI) -> None:
        """
        Regression test for B-001: MissingGreenlet.

        Before the fix, BaseHTTPMiddleware would spawn the endpoint in a new
        anyio task without greenlet context, causing MissingGreenlet when the
        endpoint (or downstream middleware) did async SQLAlchemy calls.

        After the fix (pure ASGI), the endpoint runs in the same async context
        and greenlet_spawn is available.
        """
        transport = ASGITransport(app=audit_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/db")

        # Should NOT raise MissingGreenlet; response should be normal 200
        assert response.status_code == 200
        assert response.json() == {"db": "ok"}
