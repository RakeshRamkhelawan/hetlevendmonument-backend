"""Unit tests for Foundation Portal Settings & White-Label Branding (BE-EP-047)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from starlette.requests import Request
from pydantic import ValidationError
from fastapi import HTTPException, status

from src.core.api.v1.foundation.schemas import (
    PortalSettingsResponse,
    PortalSettingsUpdateRequest,
)
from src.core.api.v1.foundation.settings import get_settings, update_settings
from src.core.models.foundation_content import (
    FoundationPortalSettings,
    PortalRole,
    PortalUser,
)
from src.core.models.rbac_models import Tenant


# ============================================================================
# Schema Validation Tests
# ============================================================================


def test_portal_settings_update_valid_payload() -> None:
    """Valid payload with hex colors and names passes validation."""
    data = {
        "platform_name_nl": "Stichting Ketikoti Vlaardingen",
        "platform_name_en": "Ketikoti Vlaardingen Foundation",
        "primary_color": "#1A2F45",
        "accent_color": "#e8b86d",
        "logo_url": "https://example.com/logo.png",
        "favicon_url": "https://example.com/favicon.ico",
        "guidelines_nl": "Respecteer andermans verhalen.",
        "about_nl": "Over onze historische herdenking.",
        "contact_email": "info@ketikoti.nl",
    }
    req = PortalSettingsUpdateRequest(**data)
    assert req.platform_name_nl == "Stichting Ketikoti Vlaardingen"
    assert req.primary_color == "#1A2F45"
    assert req.accent_color == "#e8b86d"



def _echte_request() -> Request:
    """Een echte Starlette-Request: `privacy_rate_limit` weigert een functie-aanroep zonder."""
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/test/foundation",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 50000),
        }
    )

@pytest.mark.parametrize(
    "invalid_color",
    [
        "blue",
        "#12345",
        "#1234567",
        "123456",
        "#gggggg",
        "#12 456",
    ],
)
def test_portal_settings_update_invalid_hex_color(invalid_color: str) -> None:
    """Non-conforming hex color formats raise ValidationError."""
    with pytest.raises(ValidationError):
        PortalSettingsUpdateRequest(primary_color=invalid_color)


def test_portal_settings_update_name_length_bounds() -> None:
    """Platform name exceeding 120 chars raises ValidationError."""
    with pytest.raises(ValidationError):
        PortalSettingsUpdateRequest(platform_name_nl="x" * 121)

    with pytest.raises(ValidationError):
        PortalSettingsUpdateRequest(platform_name_nl="")


# ============================================================================
# Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_settings_public_endpoint_success() -> None:
    """Public get_settings returns portal settings."""
    tenant = Tenant(id=1, slug="ketikoti", name="Ketikoti", is_active=True)
    settings = FoundationPortalSettings(
        id=1,
        tenant_id=1,
        platform_name_nl="Ketikoti Vlaardingen",
        platform_name_en="Ketikoti Foundation",
        primary_color="#1a2f45",
        accent_color="#e8b86d",
        contact_email="info@ketikoti.nl",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = settings
    mock_db.execute.return_value = mock_result

    with patch(
        "src.core.api.v1.foundation.settings.public_tenant_scope"
    ) as mock_scope:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = tenant
        mock_ctx.__aexit__.return_value = None
        mock_scope.return_value = mock_ctx

        res = await get_settings(request=_echte_request(), tenantSlug="ketikoti", session=mock_db)

        assert res["platform_name_nl"] == "Ketikoti Vlaardingen"
        assert res["primary_color"] == "#1a2f45"
        assert res["contact_email"] == "info@ketikoti.nl"


@pytest.mark.asyncio
async def test_get_settings_not_found() -> None:
    """Missing portal settings raises HTTP 404."""
    tenant = Tenant(id=1, slug="empty", name="Empty", is_active=True)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with patch(
        "src.core.api.v1.foundation.settings.public_tenant_scope"
    ) as mock_scope:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = tenant
        mock_ctx.__aexit__.return_value = None
        mock_scope.return_value = mock_ctx

        with pytest.raises(HTTPException) as exc_info:
            await get_settings(request=_echte_request(), tenantSlug="empty", session=mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_settings_success() -> None:
    """Curator can update portal settings."""
    tenant = Tenant(id=1, slug="ketikoti", name="Ketikoti", is_active=True)
    curator_user = PortalUser(
        id=10,
        tenant_id=1,
        email="curator@ketikoti.nl",
        role=PortalRole.CURATOR,
        is_blocked=False,
    )
    existing_settings = FoundationPortalSettings(
        id=1,
        tenant_id=1,
        platform_name_nl="Old Name",
        primary_color="#000000",
        accent_color="#ffffff",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_settings
    mock_db.execute.return_value = mock_result

    payload = PortalSettingsUpdateRequest(
        platform_name_nl="Nieuwe Naam",
        primary_color="#123456",
        accent_color="#abcdef",
        about_nl="Nieuwe tekst",
    )

    with patch(
        "src.core.api.v1.foundation.settings.public_tenant_scope"
    ) as mock_scope:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = tenant
        mock_ctx.__aexit__.return_value = None
        mock_scope.return_value = mock_ctx

        res = await update_settings(
            tenantSlug="ketikoti",
            payload=payload,
            current_user=curator_user,
            session=mock_db,
        )

        assert res["platform_name_nl"] == "Nieuwe Naam"
        assert res["primary_color"] == "#123456"
        assert res["accent_color"] == "#abcdef"
        assert res["about_nl"] == "Nieuwe tekst"
        mock_db.flush.assert_called_once()


@pytest.mark.asyncio
async def test_update_settings_cross_tenant_forbidden() -> None:
    """User from another tenant is rejected with HTTP 403."""
    tenant = Tenant(id=1, slug="ketikoti", name="Ketikoti", is_active=True)
    foreign_user = PortalUser(
        id=20,
        tenant_id=2,  # Different tenant!
        email="curator@other.nl",
        role=PortalRole.CURATOR,
        is_blocked=False,
    )

    mock_db = AsyncMock()
    payload = PortalSettingsUpdateRequest(platform_name_nl="Hack Attempt")

    with patch(
        "src.core.api.v1.foundation.settings.public_tenant_scope"
    ) as mock_scope:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = tenant
        mock_ctx.__aexit__.return_value = None
        mock_scope.return_value = mock_ctx

        with pytest.raises(HTTPException) as exc_info:
            await update_settings(
                tenantSlug="ketikoti",
                payload=payload,
                current_user=foreign_user,
                session=mock_db,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_update_settings_upsert_when_none_exist() -> None:
    """If tenant has no settings yet, update_settings creates a new record."""
    tenant = Tenant(id=1, slug="ketikoti", name="Ketikoti", is_active=True)
    curator_user = PortalUser(
        id=10,
        tenant_id=1,
        email="curator@ketikoti.nl",
        role=PortalRole.ADMIN,
        is_blocked=False,
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None  # No settings yet
    mock_db.execute.return_value = mock_result

    payload = PortalSettingsUpdateRequest(
        platform_name_nl="Eerste Configuratie",
        primary_color="#223344",
        accent_color="#556677",
        contact_email="admin@ketikoti.nl",
    )

    with patch(
        "src.core.api.v1.foundation.settings.public_tenant_scope"
    ) as mock_scope:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = tenant
        mock_ctx.__aexit__.return_value = None
        mock_scope.return_value = mock_ctx

        res = await update_settings(
            tenantSlug="ketikoti",
            payload=payload,
            current_user=curator_user,
            session=mock_db,
        )

        assert res["platform_name_nl"] == "Eerste Configuratie"
        assert res["primary_color"] == "#223344"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
