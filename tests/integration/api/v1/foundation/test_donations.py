"""Integration tests for Foundation Portal donations & adoption endpoints (BE-EP-046 / ADR-029 P2-2)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient

from sqlalchemy import select
from src.core.exceptions.foundation import CaptchaFailedError
from src.core.models.foundation_content import FoundationDonation


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestDonationCheckout:
    """Tests for creating Stripe donation checkout sessions."""

    async def test_checkout_one_time_donation_success(
        self,
        integration_client: AsyncClient,
        postgres_session,
    ) -> None:
        """Visitor can create a one-time donation checkout session."""
        payload = {
            "amount_cents": 2500,
            "frequency": "one_time",
            "donor_email": "vriend@example.org",
            "donor_name": "Familie De Wit",
            "is_anonymous": False,
            "message": "Voor behoud van het archief.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(
            _url("default", "/donations/checkout"),
            json=payload,
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert "checkout_url" in data
        assert "session_id" in data
        assert data["amount_cents"] == 2500
        assert data["frequency"] == "one_time"

        # Verify added to PostgreSQL database with 'pending' status
        session_id = data["session_id"]
        stmt = select(FoundationDonation).where(FoundationDonation.stripe_session_id == session_id)
        res_db = await postgres_session.execute(stmt)
        donation = res_db.scalar_one_or_none()
        assert donation is not None
        assert donation.amount_cents == 2500
        assert donation.email == "vriend@example.org"
        assert donation.status == "pending"

    async def test_checkout_monthly_donation_success(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Visitor can create a recurring monthly adoption/support session."""
        payload = {
            "amount_cents": 1500,
            "frequency": "monthly",
            "donor_email": "maandelijkse.steun@example.org",
            "donor_name": "Anoniem",
            "is_anonymous": True,
            "message": "Maandelijkse steun voor educatieve projecten.",
            "hcaptcha_token": "mock-token-123",
        }
        res = await integration_client.post(
            _url("default", "/donations/checkout"),
            json=payload,
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert "checkout_url" in data
        assert data["amount_cents"] == 1500
        assert data["frequency"] == "monthly"

    async def test_checkout_amount_out_of_range_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Amounts below 100 cents (1 EUR) or above 500.000 cents (5000 EUR) return 422."""
        # Below minimum
        res_low = await integration_client.post(
            _url("default", "/donations/checkout"),
            json={
                "amount_cents": 50,
                "frequency": "one_time",
                "donor_email": "min@example.org",
                "hcaptcha_token": "mock-token-123",
            },
        )
        assert res_low.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        # Above maximum
        res_high = await integration_client.post(
            _url("default", "/donations/checkout"),
            json={
                "amount_cents": 600000,
                "frequency": "one_time",
                "donor_email": "max@example.org",
                "hcaptcha_token": "mock-token-123",
            },
        )
        assert res_high.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_checkout_invalid_frequency_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid donation frequency returns 422."""
        res = await integration_client.post(
            _url("default", "/donations/checkout"),
            json={
                "amount_cents": 2500,
                "frequency": "quarterly",
                "donor_email": "freq@example.org",
                "hcaptcha_token": "mock-token-123",
            },
        )
        assert res.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_checkout_bot_protection_failure_returns_400(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Failed hCaptcha verification returns 400 CAPTCHA_FAILED."""
        with patch(
            "src.core.api.v1.foundation.donations.require_hcaptcha",
            side_effect=CaptchaFailedError(),
        ):
            res = await integration_client.post(
                _url("default", "/donations/checkout"),
                json={
                    "amount_cents": 2500,
                    "frequency": "one_time",
                    "donor_email": "bot@spammer.org",
                    "hcaptcha_token": "bad-token",
                },
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            data = res.json()
            err_code = data.get("error_code") or data.get("error", {}).get("error_code")
            assert err_code == "CAPTCHA_FAILED"


@pytest.mark.asyncio
@pytest.mark.integration
class TestDonationStatsAndAnonymity:
    """Tests for public statistics and anonymity masking."""

    async def test_stats_public_without_auth(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Public users can view transparency stats without authentication."""
        res = await integration_client.get(_url("default", "/donations/stats"))
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert "total_raised_cents" in data
        assert "total_donations_count" in data
        assert "monthly_supporters_count" in data
        assert isinstance(data["recent_donations"], list)

    async def test_stats_anonymity_masking_rule(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Anonymous donors are masked as 'Anonieme Vriend van het Monument' with email excluded."""
        # Create anonymous donation
        checkout_res = await integration_client.post(
            _url("default", "/donations/checkout"),
            json={
                "amount_cents": 3500,
                "frequency": "one_time",
                "donor_email": "secret.donor@privatemail.com",
                "donor_name": "Geheime Naam",
                "is_anonymous": True,
                "message": "Geheime steun",
                "hcaptcha_token": "mock-token-123",
            },
        )
        assert checkout_res.status_code == status.HTTP_200_OK
        session_id = checkout_res.json()["session_id"]

        # Finalize donation via Stripe webhook
        webhook_res = await integration_client.post(
            _url("default", "/donations/webhook"),
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": session_id,
                        "payment_intent": "pi_mock_anon_123",
                    }
                },
            },
        )
        assert webhook_res.status_code == status.HTTP_200_OK

        res = await integration_client.get(_url("default", "/donations/stats"))
        assert res.status_code == status.HTTP_200_OK
        data = res.json()

        # Find the donation in recent list
        matched = [
            d
            for d in data["recent_donations"]
            if d["amount_cents"] == 3500 and d["is_anonymous"] is True
        ]
        assert len(matched) >= 1
        item = matched[0]
        assert item["donor_name"] == "Anonieme Vriend van het Monument"
        # STRICT PRIVACY INVARIANT: email address must NEVER appear in public response
        assert "secret.donor@privatemail.com" not in str(res.json())

    async def test_stats_named_supporter_display(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Non-anonymous donors have their display name shown publicly."""
        checkout_res = await integration_client.post(
            _url("default", "/donations/checkout"),
            json={
                "amount_cents": 4200,
                "frequency": "one_time",
                "donor_email": "publiek@erfgoedstichting.nl",
                "donor_name": "Stichting Historisch Erfgoed",
                "is_anonymous": False,
                "message": "Trots op het project!",
                "hcaptcha_token": "mock-token-123",
            },
        )
        assert checkout_res.status_code == status.HTTP_200_OK
        session_id = checkout_res.json()["session_id"]

        # Finalize donation via Stripe webhook
        webhook_res = await integration_client.post(
            _url("default", "/donations/webhook"),
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": session_id,
                        "payment_intent": "pi_mock_named_456",
                    }
                },
            },
        )
        assert webhook_res.status_code == status.HTTP_200_OK

        res = await integration_client.get(_url("default", "/donations/stats"))
        assert res.status_code == status.HTTP_200_OK
        matched = [d for d in res.json()["recent_donations"] if d["amount_cents"] == 4200]
        assert len(matched) >= 1
        assert matched[0]["donor_name"] == "Stichting Historisch Erfgoed"

    async def test_stripe_webhook_flow(
        self,
        integration_client: AsyncClient,
        postgres_session,
    ) -> None:
        """Stripe webhook checkout.session.completed marks pending donation as completed."""
        checkout_res = await integration_client.post(
            _url("default", "/donations/checkout"),
            json={
                "amount_cents": 5000,
                "frequency": "one_time",
                "donor_email": "webhook.tester@example.org",
                "donor_name": "Webhook Tester",
                "is_anonymous": False,
                "message": "Test webhook",
                "hcaptcha_token": "mock-token-123",
            },
        )
        session_id = checkout_res.json()["session_id"]

        # Initial status in DB is pending
        stmt = select(FoundationDonation).where(FoundationDonation.stripe_session_id == session_id)
        d_before = (await postgres_session.execute(stmt)).scalar_one()
        assert d_before.status == "pending"
        assert d_before.completed_at is None

        # Trigger webhook
        wh_res = await integration_client.post(
            _url("default", "/donations/webhook"),
            json={
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "id": session_id,
                        "payment_intent": "pi_test_webhook_789",
                    }
                },
            },
        )
        assert wh_res.status_code == status.HTTP_200_OK
        assert wh_res.json()["received"] is True

        # Refresh from DB
        await postgres_session.refresh(d_before)
        assert d_before.status == "completed"
        assert d_before.completed_at is not None
        assert d_before.stripe_payment_intent_id == "pi_test_webhook_789"


@pytest.mark.asyncio
@pytest.mark.integration
class TestDonationAdminAndRBAC:
    """Tests for curator and admin donation inspection endpoints."""

    async def test_admin_donations_unauthenticated_forbidden(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Unauthenticated request to admin donations endpoint is rejected."""
        res = await integration_client.get(_url("default", "/admin/donations"))
        assert res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    async def test_admin_donations_visitor_forbidden(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
    ) -> None:
        """Regular visitor cannot access the curator audit endpoint."""
        res = await integration_client.get(
            _url("default", "/admin/donations"),
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN

    async def test_admin_donations_curator_allowed_unmasked(
        self,
        integration_client: AsyncClient,
        portal_curator_token: str,
    ) -> None:
        """Curator can access full audit list including unmasked donor emails and names."""
        res = await integration_client.get(
            _url("default", "/admin/donations"),
            headers={"Authorization": f"Bearer {portal_curator_token}"},
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        # Curator sees donor_email for fiscal bookkeeping
        if len(data["items"]) > 0:
            assert "donor_email" in data["items"][0]


@pytest.mark.asyncio
@pytest.mark.integration
class TestDonationMultiTenant:
    """Tests for multi-tenant isolation on donations."""

    async def test_unknown_tenant_returns_404(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Non-existent tenant returns 404."""
        res = await integration_client.get(_url("onbekende-stichting-donaties", "/donations/stats"))
        assert res.status_code == status.HTTP_404_NOT_FOUND
        data = res.json()
        err_code = data.get("error_code") or data.get("error", {}).get("error_code")
        assert err_code == "TENANT_NOT_FOUND"
