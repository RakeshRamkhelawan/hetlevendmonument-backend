"""
Conftest for focus_builder API v1 tests.

Provides an `auth_client` fixture: a lightweight FastAPI ASGI test client
with the focus-builder router mounted and auth/tenant dependencies overridden.
"""

from typing import AsyncGenerator
from unittest.mock import MagicMock

import httpx
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient


@pytest_asyncio.fixture
async def auth_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Authenticated AsyncClient against a minimal FastAPI app with the
    focus-builder router (including the agents sub-router).

    Auth and tenant dependencies are overridden so no real DB/JWT is needed.
    """
    from src.core.api.v1.focus_builder.router import router as fb_router
    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.middleware.tenant_context import get_current_tenant_id

    app = FastAPI()
    app.include_router(fb_router, prefix="/api/v1")

    # Mock user
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.tenant_id = 1
    mock_user.email = "test@example.com"

    async def override_user():
        return mock_user

    def override_tenant_id():
        return 1

    app.dependency_overrides[get_current_user_dependency] = override_user
    app.dependency_overrides[get_current_tenant_id] = override_tenant_id

    transport = httpx.ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
