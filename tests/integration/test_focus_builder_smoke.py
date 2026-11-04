"""
FocusBuilder smoke integration tests.

Verifies that read-only Focus Builder endpoints return 200 without needing
ActivePieces credentials or a configured ActivePieces instance.
"""

from collections.abc import AsyncGenerator
from typing import Any, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def focus_builder_authenticated_client(
    integration_app: FastAPI,
    postgres_session: AsyncSession,
    admin_token: str,
) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated client for Focus Builder endpoints.

    Overrides DB and auth dependencies so no real JWT or ActivePieces
    configuration is required. Sends a valid bearer token so the
    TenantMiddleware can resolve the tenant context.
    """
    from src.core.api.dependencies import get_db as api_get_db
    from src.core.api.v1.focus_builder.shared import get_focus_builder_service
    from src.core.auth.dependencies import get_current_user_dependency
    from src.core.database.database import get_db
    from src.core.database.session import get_db_session

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield postgres_session

    async def override_get_current_user() -> SimpleNamespace:
        return SimpleNamespace(
            id=1,
            email="admin@integration.test",
            tenant_id=1,
            is_active=True,
            is_superuser=True,
            roles=["admin"],
        )

    mock_service = MagicMock()
    mock_service.repository = MagicMock()
    mock_service.repository.list = AsyncMock(return_value=[])
    mock_service.get_pieces_catalog = AsyncMock(return_value=[])

    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[api_get_db] = override_get_db
    integration_app.dependency_overrides[get_db_session] = override_get_db
    integration_app.dependency_overrides[get_current_user_dependency] = override_get_current_user
    integration_app.dependency_overrides[get_focus_builder_service] = lambda: mock_service

    transport = ASGITransport(app=integration_app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        follow_redirects=True,
        headers={"Authorization": f"Bearer {admin_token}"},
    ) as client:
        yield client

    deps: list[Callable[..., Any]] = [
        get_db,
        api_get_db,
        get_db_session,
        get_current_user_dependency,
        get_focus_builder_service,
    ]
    for dep in deps:
        if dep in integration_app.dependency_overrides:
            del integration_app.dependency_overrides[dep]


@pytest.mark.asyncio
async def test_list_flows_returns_empty_list(
    focus_builder_authenticated_client: AsyncClient,
) -> None:
    """GET /focus-builder/flows returns 200 and an empty list without AP calls."""
    resp = await focus_builder_authenticated_client.get("/api/v1/focus-builder/flows")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body == []


@pytest.mark.asyncio
async def test_list_pieces_returns_empty_catalog(
    focus_builder_authenticated_client: AsyncClient,
) -> None:
    """GET /focus-builder/pieces returns 200 and an empty catalog without AP calls."""
    resp = await focus_builder_authenticated_client.get("/api/v1/focus-builder/pieces")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pieces"] == []
    assert body["total"] == 0
