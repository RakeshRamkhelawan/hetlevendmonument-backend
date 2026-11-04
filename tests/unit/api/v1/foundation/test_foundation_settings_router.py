"""Unit tests for Foundation Portal settings router (src/core/api/v1/foundation/settings.py).

Covers:
- GET /settings
"""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.foundation.settings import get_settings, router
from tests.helpers.limiet_request import echte_request


class DummyTenant:
    def __init__(self, id: int = 1) -> None:
        self.id = id


class DummySettings:
    def __init__(self) -> None:
        self.platform_name_nl = "Platform NL"
        self.platform_name_en = "Platform EN"
        self.primary_color = "#123456"
        self.accent_color = "#abcdef"
        self.logo_url = "https://example.com/logo.png"
        self.favicon_url = "https://example.com/favicon.ico"
        self.guidelines_nl = "Richtlijnen"
        self.guidelines_en = "Guidelines"
        self.about_nl = "Over ons"
        self.about_en = "About us"
        self.contact_email = "support@example.com"


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/settings" in paths


@pytest.mark.asyncio
async def test_get_settings_not_found_returns_404() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    tenant = DummyTenant(id=1)

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.settings.public_tenant_scope", side_effect=mock_scope):
        with pytest.raises(HTTPException) as exc_info:
            await get_settings(request=echte_request(), tenantSlug="test-tenant", session=session)
        assert exc_info.value.status_code == 404
        assert "Portal settings not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_settings_success() -> None:
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = DummySettings()
    session.execute.return_value = mock_result

    tenant = DummyTenant(id=1)

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.settings.public_tenant_scope", side_effect=mock_scope):
        res = await get_settings(request=echte_request(), tenantSlug="test-tenant", session=session)
        assert res["platform_name_nl"] == "Platform NL"
        assert res["primary_color"] == "#123456"
        assert res["contact_email"] == "support@example.com"
