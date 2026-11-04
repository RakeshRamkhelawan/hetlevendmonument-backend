"""Integration tests for Foundation Portal contact endpoint (BE-EP-048 / ADR-029 P2)."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient

from sqlalchemy import select
from src.core.exceptions.foundation import CaptchaFailedError
from src.core.models.foundation_content import (
    FoundationContactSubmission,
    FoundationPortalSettings,
)


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestContactSubmissionSuccess:
    """Tests for successful contact inquiries."""

    async def test_submit_contact_inquiry_minimal(
        self,
        integration_client: AsyncClient,
        postgres_session,
    ) -> None:
        """Visitor can submit a valid contact inquiry and receive reference ID."""
        payload = {
            "name": "Jan de Vries",
            "email": "jan@voorbeeld.nl",
            "subject": "Vraag over historisch archief",
            "category": "algemeen",
            "message": "Ik wil graag meer informatie over het archief van Vlaardingen.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(_url("default", "/contact"), json=payload)
        assert res.status_code == status.HTTP_200_OK

        data = res.json()
        assert data["status"] == "received"
        assert "ontvangen" in data["message"]
        assert "created_at" in data

        # Validate reference ID pattern: CON-YYYYMMDD-XXXX
        reference_id = data["reference_id"]
        assert re.match(r"^CON-\d{8}-[0-9A-F]{4}$", reference_id)

        # Verify stored in database (default tenant_id = 1)
        stmt = select(FoundationContactSubmission).where(
            FoundationContactSubmission.reference_number == reference_id
        )
        result = await postgres_session.execute(stmt)
        submission = result.scalar_one_or_none()
        assert submission is not None
        assert submission.name == "Jan de Vries"
        assert submission.email == "jan@voorbeeld.nl"
        assert submission.subject == "Vraag over historisch archief"
        assert submission.category == "algemeen"
        assert submission.tenant_id == 1

    async def test_submit_contact_inquiry_with_portal_settings_and_brevo_dispatch(
        self,
        integration_client: AsyncClient,
        portal_settings: FoundationPortalSettings,
    ) -> None:
        """Submission dispatches both confirmation and notification emails via Brevo."""
        payload = {
            "name": "Amina Al-Sayed",
            "email": "amina@voorbeeld.nl",
            "subject": "Educatief project basisschool",
            "category": "educatie",
            "message": "Wij willen graag met onze groep 8 het herdenkingsmonument bezoeken.",
            "hcaptcha_token": "mock-token-123",
        }

        with (
            patch(
                "src.core.api.v1.foundation.contact.brevo_email_service.send_contact_confirmation",
                new_callable=AsyncMock,
            ) as mock_confirm,
            patch(
                "src.core.api.v1.foundation.contact.brevo_email_service.send_contact_notification",
                new_callable=AsyncMock,
            ) as mock_notify,
        ):
            res = await integration_client.post(_url("default", "/contact"), json=payload)
            assert res.status_code == status.HTTP_200_OK
            ref_id = res.json()["reference_id"]

            # Verify confirmation email was dispatched to sender
            mock_confirm.assert_awaited_once()
            confirm_args = mock_confirm.await_args[1]
            assert confirm_args["to_email"] == "amina@voorbeeld.nl"
            assert confirm_args["reference_id"] == ref_id
            assert confirm_args["sender_name"] == "Amina Al-Sayed"

            # Verify notification email was dispatched to foundation contact_email
            mock_notify.assert_awaited_once()
            notify_args = mock_notify.await_args[1]
            assert notify_args["to_email"] == portal_settings.contact_email
            assert notify_args["reference_id"] == ref_id
            assert notify_args["sender_email"] == "amina@voorbeeld.nl"
            assert notify_args["category"] == "educatie"

    async def test_all_allowed_categories_accepted(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """All predefined categories are accepted by the endpoint."""
        categories = ["algemeen", "educatie", "donatie", "archief", "samenwerking"]
        for cat in categories:
            payload = {
                "name": f"Tester {cat}",
                "email": f"test_{cat}@voorbeeld.nl",
                "subject": f"Onderwerp {cat}",
                "category": cat,
                "message": f"Dit is een geldig testbericht voor categorie {cat}.",
                "hcaptcha_token": "mock-token-123",
            }
            res = await integration_client.post(_url("default", "/contact"), json=payload)
            assert res.status_code == status.HTTP_200_OK, f"Category '{cat}' should be accepted"


@pytest.mark.asyncio
@pytest.mark.integration
class TestContactSubmissionValidation:
    """Tests for payload schema validation errors."""

    async def test_submit_invalid_email_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Malformed email returns 422 Unprocessable Content."""
        payload = {
            "name": "Jan",
            "email": "geen-geldig-emailadres",
            "subject": "Vraag",
            "category": "algemeen",
            "message": "Dit is een geldig bericht van voldoende lengte.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(_url("default", "/contact"), json=payload)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_submit_short_message_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Message shorter than 10 chars returns 422."""
        payload = {
            "name": "Jan",
            "email": "jan@voorbeeld.nl",
            "subject": "Vraag",
            "category": "algemeen",
            "message": "Te kort",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(_url("default", "/contact"), json=payload)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_submit_invalid_category_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Non-whitelisted category returns 422."""
        payload = {
            "name": "Jan",
            "email": "jan@voorbeeld.nl",
            "subject": "Vraag",
            "category": "ongeldige_categorie",
            "message": "Dit is een geldig bericht van voldoende lengte.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(_url("default", "/contact"), json=payload)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_submit_missing_required_fields_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Missing required subject field returns 422."""
        payload = {
            "name": "Jan",
            "email": "jan@voorbeeld.nl",
            "category": "algemeen",
            "message": "Dit is een geldig bericht van voldoende lengte.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(_url("default", "/contact"), json=payload)
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
@pytest.mark.integration
class TestContactBotProtectionAndRateLimits:
    """Tests for bot protection and rate limiting."""

    async def test_submit_failed_captcha_returns_400(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Failed hCaptcha verification returns 400 CAPTCHA_FAILED."""
        payload = {
            "name": "Bot Spammer",
            "email": "spammer@bot.org",
            "subject": "Buy crypto",
            "category": "algemeen",
            "message": "Dit is geautomatiseerde spam tekst van tien tekens.",
            "hcaptcha_token": "invalid-token",
        }
        with patch(
            "src.core.api.v1.foundation.contact.require_hcaptcha",
            side_effect=CaptchaFailedError(),
        ):
            res = await integration_client.post(_url("default", "/contact"), json=payload)
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            data = res.json()
            err_code = data.get("error_code") or data.get("error", {}).get("error_code")
            assert err_code == "CAPTCHA_FAILED"

    async def test_submit_rate_limit_exceeded_returns_429(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Exceeding 30 requests per minute from same IP returns 429."""
        payload = {
            "name": "Rate Tester",
            "email": "rate@voorbeeld.nl",
            "subject": "Rate limit check",
            "category": "algemeen",
            "message": "Bericht voor rate limit verificatie van voldoende lengte.",
            "hcaptcha_token": "mock-token-123",
        }
        for i in range(10):
            res = await integration_client.post(_url("default", "/contact"), json=payload)
            assert res.status_code == status.HTTP_200_OK, f"Request {i + 1} should succeed"

        # 11th request should be throttled
        res11 = await integration_client.post(_url("default", "/contact"), json=payload)
        assert res11.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Retry-After" in res11.headers


@pytest.mark.asyncio
@pytest.mark.integration
class TestContactMultiTenantIsolation:
    """Tests for multi-tenant isolation and routing."""

    async def test_submit_unknown_tenant_returns_404(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Non-existent tenant slug returns 404 TENANT_NOT_FOUND."""
        payload = {
            "name": "Jan",
            "email": "jan@voorbeeld.nl",
            "subject": "Vraag",
            "category": "algemeen",
            "message": "Bericht voor onbekende stichting van voldoende lengte.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(
            _url("niet-bestaande-stichting-xyz", "/contact"), json=payload
        )
        assert res.status_code == status.HTTP_404_NOT_FOUND
        data = res.json()
        err_code = data.get("error_code") or data.get("error", {}).get("error_code")
        assert err_code == "TENANT_NOT_FOUND"
