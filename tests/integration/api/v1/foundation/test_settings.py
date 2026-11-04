"""Integration tests for Foundation Portal settings endpoint."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from src.core.models.foundation_content import FoundationPortalSettings


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# ============================================================================
# Settings endpoint (GET /{tenantSlug}/foundation/settings)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestPortalSettings:
    """Tests for the public portal settings endpoint."""

    async def test_get_settings_success(
        self,
        integration_client: AsyncClient,
        portal_settings: FoundationPortalSettings,
    ) -> None:
        """Public users can retrieve portal settings."""
        response = await integration_client.get(_url("default", "/settings"))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["platform_name_nl"] == "Ketikoti Vlaardingen"
        assert data["contact_email"] == "info@ketikotivlaardingen.nl"
        assert data["primary_color"] == "#1a2f45"
        assert data["accent_color"] == "#e8b86d"

    async def test_get_settings_no_auth_required(
        self,
        integration_client: AsyncClient,
        portal_settings: FoundationPortalSettings,
    ) -> None:
        """No authentication required for settings."""
        response = await integration_client.get(_url("default", "/settings"))
        assert response.status_code == status.HTTP_200_OK

    async def test_get_settings_invalid_tenant(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid tenant slug returns 404."""
        response = await integration_client.get(_url("nonexistent", "/settings"))
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_get_settings_missing_settings(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Tenant without settings returns 404.

        Uses "other" (tenant_id=2, pre-seeded secondary tenant -- see
        tests/integration/conftest.py), not "othertenant": that slug doesn't
        exist, so the previous version of this test passed for the wrong
        reason ("tenant not found" instead of "tenant found, no settings" --
        both return 404, so the assertion couldn't tell them apart).
        """
        response = await integration_client.get(_url("other", "/settings"))
        assert response.status_code == status.HTTP_404_NOT_FOUND
