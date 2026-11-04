"""Unit tests for Foundation Contact Form & Support endpoint (BE-EP-048 / ADR-029 P2).

Aligned with the current DB-backed implementation (FoundationContactSubmission);
the previous version imported the removed in-memory buffer _TENANT_CONTACT_SUBMISSIONS
and therefore failed collection.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from fastapi import HTTPException
from pydantic import ValidationError

from src.core.api.v1.foundation.contact import (
    list_contact_submissions,
    submit_contact_inquiry,
)
from src.core.api.v1.foundation.schemas import (
    ContactSubmissionRequest,
    ContactSubmissionResponse,
)
from src.core.models.foundation_content import (
    FoundationContactSubmission,
    PortalRole,
    PortalUser,
)
from src.core.shared.public_registry import PublicEndpointRegistry


def _make_tenant(id: int = 42, slug: str = "erfgoed") -> MagicMock:
    tenant = MagicMock()
    tenant.id = id
    tenant.slug = slug
    tenant.name = "Stichting Erfgoed"
    return tenant


def _patch_scope(mock_scope: MagicMock, tenant: MagicMock) -> None:
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = tenant
    mock_ctx.__aexit__.return_value = None
    mock_scope.return_value = mock_ctx


def test_contact_submission_request_valid() -> None:
    """Test valid contact submission request payload."""
    req = ContactSubmissionRequest(
        name="Jan de Vries",
        email="jan@voorbeeld.nl",
        subject="Vraag over archief",
        category="archief",
        message="Ik heb een historische foto van de haven uit 1955 die ik wil delen.",
        hcaptcha_token="mock-token-123",
    )
    assert req.name == "Jan de Vries"
    assert req.email == "jan@voorbeeld.nl"
    assert req.category == "archief"


def test_contact_submission_request_invalid_email() -> None:
    """Test validation failure on invalid email format."""
    with pytest.raises(ValidationError):
        ContactSubmissionRequest(
            name="Jan de Vries",
            email="geen-geldig-email",
            subject="Vraag over archief",
            category="archief",
            message="Dit is een testbericht van voldoende lengte.",
        )


def test_contact_submission_request_message_too_short() -> None:
    """Test validation failure when message is shorter than 10 characters."""
    with pytest.raises(ValidationError):
        ContactSubmissionRequest(
            name="Jan",
            email="jan@voorbeeld.nl",
            subject="Korte vraag",
            category="algemeen",
            message="Te kort",
        )


def test_contact_submission_request_invalid_category() -> None:
    """Test validation failure on unrecognized category."""
    with pytest.raises(ValidationError):
        ContactSubmissionRequest(
            name="Jan de Vries",
            email="jan@voorbeeld.nl",
            subject="Vraag",
            category="onbekend",  # type: ignore[arg-type]
            message="Dit is een geldig bericht van voldoende lengte.",
        )



def _echte_request() -> Request:
    """Een echte Starlette-Request: `privacy_rate_limit` weigert een functie-aanroep zonder."""
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/test/foundation",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 50000),
        }
    )

@pytest.mark.asyncio
async def test_submit_contact_inquiry_endpoint_success() -> None:
    """Successful submission persists a FoundationContactSubmission row and replies."""
    mock_tenant = _make_tenant()

    mock_db = AsyncMock()
    settings_result = MagicMock()
    settings_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = settings_result

    mock_request = _echte_request()

    req_data = ContactSubmissionRequest(
        name="Maria Alida",
        email="maria@voorbeeld.sr",
        subject="Samenwerking schoolproject",
        category="educatie",
        message="Wij willen graag met onze havo-klas een gastles organiseren.",
        hcaptcha_token="mock-valid-token",
    )

    with (
        patch(
            "src.core.api.v1.foundation.contact.require_hcaptcha", new_callable=AsyncMock
        ) as mock_captcha,
        patch("src.core.api.v1.foundation.contact.public_tenant_scope") as mock_scope,
        patch(
            "src.core.api.v1.foundation.contact.brevo_email_service", new_callable=AsyncMock
        ) as mock_brevo,
    ):
        _patch_scope(mock_scope, mock_tenant)

        resp: ContactSubmissionResponse = await submit_contact_inquiry(
            tenantSlug="erfgoed",
            request=mock_request,
            data=req_data,
            session=mock_db,
        )

        mock_captcha.assert_awaited_once_with("mock-valid-token", remote_ip="127.0.0.1")
        assert resp.status == "received"
        assert re.match(r"^CON-\d{8}-[0-9A-F]{4}$", resp.reference_id)
        assert "succesvol ontvangen" in resp.message

        # Persisted to the database (no in-memory buffer anymore)
        assert mock_db.add.called
        stored = mock_db.add.call_args.args[0]
        assert isinstance(stored, FoundationContactSubmission)
        assert stored.tenant_id == 42
        assert stored.reference_number == resp.reference_id
        assert stored.category == "educatie"
        assert stored.email == "maria@voorbeeld.sr"
        assert mock_db.commit.await_count >= 1

        # Confirmation email attempted (best-effort)
        mock_brevo.send_contact_confirmation.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_contact_submissions_endpoint() -> None:
    """Admin list returns stored submissions for the tenant."""
    mock_tenant = _make_tenant()
    curator = MagicMock(spec=PortalUser)
    curator.id = 7
    curator.role = PortalRole.CURATOR
    curator.tenant_id = mock_tenant.id

    row = MagicMock()
    row.id = 1
    row.reference_number = "CON-20260912-AB12"
    row.name = "Jan de Vries"
    row.email = "jan@voorbeeld.nl"
    row.subject = "Vraag"
    row.category = "archief"
    row.message = "Bericht"
    row.created_at = None

    mock_db = AsyncMock()
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [row]
    mock_db.execute.return_value = list_result

    with patch("src.core.api.v1.foundation.contact.public_tenant_scope") as mock_scope:
        _patch_scope(mock_scope, mock_tenant)

        res = await list_contact_submissions(
            tenantSlug="erfgoed",
            current_user=curator,
            session=mock_db,
        )

    assert res["total"] == 1
    assert res["items"][0]["reference_number"] == "CON-20260912-AB12"


@pytest.mark.asyncio
async def test_list_contact_submissions_rejects_cross_tenant_curator() -> None:
    """BE-SEC-056: een curator van tenant A krijgt 403 op de contact-lijst van tenant B.

    Rood voor de fix: de endpoint filterde alleen de query op de pad-tenant en
    vergeleek de token-tenant nooit -- namen, e-mails en berichten van een
    andere tenant waren uitleesbaar met een geldige curator-JWT.
    """
    mock_tenant = _make_tenant(id=42)
    vreemde_curator = MagicMock(spec=PortalUser)
    vreemde_curator.id = 8
    vreemde_curator.role = PortalRole.CURATOR
    vreemde_curator.tenant_id = 999

    mock_db = AsyncMock()

    with patch("src.core.api.v1.foundation.contact.public_tenant_scope") as mock_scope:
        _patch_scope(mock_scope, mock_tenant)

        with pytest.raises(HTTPException) as exc_info:
            await list_contact_submissions(
                tenantSlug="erfgoed",
                current_user=vreemde_curator,
                session=mock_db,
            )

    assert exc_info.value.status_code == 403
    mock_db.execute.assert_not_called()


def test_contact_endpoint_public_registry_rule() -> None:
    """Verify that /{tenantSlug}/foundation/contact is treated as public by PublicEndpointRegistry."""
    assert PublicEndpointRegistry.is_public("/erfgoed/foundation/contact") is True
    assert PublicEndpointRegistry.is_public("/ketikoti/foundation/contact") is True
    # Admin prefix remains protected
    assert PublicEndpointRegistry.is_public("/erfgoed/foundation/admin/contact") is False
