"""Functional contract test for POST /verify-token under the real rate limiter.

Background (OP-11, 2026-07-31): verify_token_endpoint named its Pydantic body
parameter `request`, so slowapi's wrapper -- which does
`isinstance(kwargs.get("request"), starlette.Request)` before checking limits --
raised on every single call. The endpoint returned HTTP 500 for every request,
including valid ones, and no test covered it (only a type-contract test on the
module source existed).

This test exercises the endpoint through the real @auth_limiter.limit decorator
so the slowapi contract is verified end-to-end, not by inspecting source.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.api.auth import router_token
from src.core.api.auth.dependencies import get_db


@pytest.fixture
def verified_user() -> MagicMock:
    """A User row as returned by the tenant-scoped lookup in the endpoint."""
    user = MagicMock()
    user.id = 1
    user.email = "loes@sanskritisetu.org"
    user.tenant_id = 42
    return user


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, verified_user: MagicMock) -> FastAPI:
    """Minimal app mounting the real token router with boundaries mocked."""
    exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    monkeypatch.setattr(
        router_token.jwt_handler,
        "verify_token",
        lambda *_args: {"sub": "1", "tenant_id": 42, "exp": exp},
    )
    monkeypatch.setattr(
        router_token.oauth2_service,
        "is_token_valid",
        AsyncMock(return_value=True),
    )

    # Het endpoint doet sinds ADR-036 OP-154 stap 2b TWEE opzoekingen, en de mock moet
    # die vorm volgen:
    #   1. via `pre_auth_lookup` alleen `(id, tenant_id)`  -> `.one_or_none()`
    #   2. daarna, met de klant aangenomen, de volle rij   -> `.scalar_one_or_none()`
    # Beide lopen over dezelfde gemockte sessie, want zonder ingerichte omzeilverbinding
    # levert `pre_auth_lookup` gewoon de meegegeven sessie op.
    kolommen = MagicMock()
    kolommen.id = verified_user.id
    kolommen.tenant_id = verified_user.tenant_id

    result = MagicMock()
    result.one_or_none.return_value = kolommen
    result.scalar_one_or_none.return_value = verified_user
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    async def _override_get_db() -> Any:
        yield db

    fastapi_app = FastAPI()
    fastapi_app.include_router(router_token.router)
    fastapi_app.dependency_overrides[get_db] = _override_get_db
    return fastapi_app


@pytest.mark.asyncio
async def test_verify_token_returns_200_under_real_rate_limiter(app: FastAPI) -> None:
    """A valid token must verify -- not blow up inside slowapi's wrapper."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/verify-token", json={"token": "valid.jwt.token"})

    assert response.status_code == 200, (
        "verify-token moet 200 geven voor een geldig token; kreeg "
        f"{response.status_code} ({response.text[:200]})"
    )
    assert response.json() == {"valid": True, "tenantId": "42", "userId": "1"}


@pytest.mark.asyncio
async def test_verify_token_emits_ratelimit_headers(app: FastAPI) -> None:
    """headers_enabled=True is pointless if the endpoint cannot receive the headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/verify-token", json={"token": "valid.jwt.token"})

    assert "x-ratelimit-limit" in {k.lower() for k in response.headers}, (
        "slowapi is geconfigureerd met headers_enabled=True, dus het endpoint moet "
        f"X-RateLimit-*-headers terugsturen; kreeg: {sorted(response.headers)}"
    )
