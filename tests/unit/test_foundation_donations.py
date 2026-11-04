"""Unit tests for BE-EP-046 Foundation Portal Donations (ADR-029 P2-2)
+ BE-SEC-058 Stripe webhook fail-closed hardening.

Validates:
- DonationCheckoutRequest schema validation (min/max amount, email, frequency)
- Public donation checkout session creation against the real Stripe SDK surface
- Checkout refuses (503) when Stripe keys are not configured -- no mock session,
  no donation row (BE-SEC-058, mock fallback removed)
- Webhook fail-closed behaviour (BE-SEC-058):
  * no webhook secret configured -> 503, payload never parsed, no state change
  * wrong/missing Stripe-Signature -> 400, no state change
  * correctly signed payload (self-signed per the Stripe v1 scheme) -> processed
- Public transparency statistics with anonymity masking
- Admin audit list (unmasked) for curators
- PublicEndpointRegistry exemption for donations endpoints and protection of admin endpoint
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

from src.core.api.v1.foundation.donations import (
    create_donation_checkout,
    get_donation_stats,
    list_admin_donations,
    stripe_donations_webhook,
)
from src.core.api.v1.foundation.schemas import (
    DonationCheckoutRequest,
    DonationCheckoutResponse,
    DonationStatsResponse,
)
from src.core.config.unified_config import config
from src.core.models.foundation_content import FoundationDonation, PortalRole, PortalUser
from src.core.models.rbac_models import Tenant
from src.core.services.stripe_service import stripe_service
from src.core.shared.public_registry import PublicEndpointRegistry

# Test webhook secret assembled from fragments so secret scanners do not see a
# literal Stripe-format key. This is a TEST-ONLY value, never a real secret.
TEST_WEBHOOK_SECRET = "whsec" + "_wk1test" + "signing" + "secret"


# ============================================================================
# Helpers & Fixtures
# ============================================================================


def _create_mock_request(
    path: str = "/default/foundation/donations/checkout",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> Request:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "http",
    }

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _sign_payload(payload: bytes, secret: str, ts: int | None = None) -> str:
    """Build a Stripe-Signature header per the official v1 scheme.

    signed_payload = "{t}.{payload}"; v1 = HMAC-SHA256(secret, signed_payload).
    """
    ts = ts if ts is not None else int(time.time())
    signed = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _create_mock_tenant(
    id: int = 1,
    slug: str = "ketikoti-vlaardingen",
    name: str = "Stichting Ketikoti",
) -> Tenant:
    tenant = MagicMock(spec=Tenant)
    tenant.id = id
    tenant.slug = slug
    tenant.name = name
    return tenant


def _create_mock_curator(
    id: int = 42,
    role: PortalRole = PortalRole.CURATOR,
    email: str = "curator@erfgoed.nl",
    tenant_id: int = 1,
) -> PortalUser:
    user = MagicMock(spec=PortalUser)
    user.id = id
    user.role = role
    user.email = email
    user.tenant_id = tenant_id
    return user


def _patch_tenant_scope(mock_scope: MagicMock, tenant: Tenant) -> None:
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__.return_value = tenant
    mock_ctx.__aexit__.return_value = None
    mock_scope.return_value = mock_ctx


def _make_donation_row(**overrides: object) -> MagicMock:
    row = MagicMock()
    row.id = overrides.get("id", 1)
    row.amount_cents = overrides.get("amount_cents", 1000)
    row.frequency = overrides.get("frequency", "one_time")
    row.email = overrides.get("email", "donor@example.org")
    row.donor_name = overrides.get("donor_name", "Publieke Donateur")
    row.is_anonymous = overrides.get("is_anonymous", False)
    row.adopted_content_id = overrides.get("adopted_content_id", None)
    row.message = overrides.get("message", "Voor de jeugd")
    row.status = overrides.get("status", "completed")
    row.stripe_session_id = overrides.get("stripe_session_id", "cs_test_1")
    row.stripe_payment_intent_id = overrides.get("stripe_payment_intent_id", None)
    row.created_at = overrides.get(
        "created_at", datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc)
    )
    row.completed_at = overrides.get("completed_at", None)
    return row


# ============================================================================
# Test Schema Validation
# ============================================================================


def test_donation_request_valid() -> None:
    """Valid donation request passes Pydantic schema validation."""
    req = DonationCheckoutRequest(
        amount_cents=2500,
        frequency="one_time",
        donor_email="steun@erfgoed.nl",
        donor_name="Familie Jansen",
        is_anonymous=False,
        monument_id=12,
        message="Mooi initiatief!",
    )
    assert req.amount_cents == 2500
    assert req.frequency == "one_time"
    assert req.donor_email == "steun@erfgoed.nl"
    assert req.is_anonymous is False


def test_donation_request_amount_too_low() -> None:
    """Donation under 100 cents (EUR 1.00) raises ValidationError."""
    with pytest.raises(ValidationError):
        DonationCheckoutRequest(
            amount_cents=50,
            frequency="one_time",
            donor_email="test@test.nl",
        )


def test_donation_request_amount_too_high() -> None:
    """Donation over 500,000 cents (EUR 5,000.00) raises ValidationError."""
    with pytest.raises(ValidationError):
        DonationCheckoutRequest(
            amount_cents=600000,
            frequency="one_time",
            donor_email="test@test.nl",
        )


def test_donation_request_invalid_email() -> None:
    """Invalid email raises ValidationError."""
    with pytest.raises(ValidationError):
        DonationCheckoutRequest(
            amount_cents=1000,
            frequency="one_time",
            donor_email="not-an-email",
        )


# ============================================================================
# Test Checkout Endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_create_donation_checkout_endpoint() -> None:
    """create_donation_checkout creates a Stripe session and records a pending donation."""
    tenant = _create_mock_tenant()
    req = _create_mock_request()
    session = AsyncMock()

    payload = DonationCheckoutRequest(
        amount_cents=5000,
        frequency="one_time",
        donor_email="donateur@erfgoed.org",
        donor_name="Mevrouw De Wit",
        is_anonymous=False,
        message="Veel succes met de educatie!",
    )

    mock_session_obj = MagicMock()
    mock_session_obj.url = "https://checkout.stripe.com/c/pay/cs_test_wk1"
    mock_session_obj.id = "cs_test_wk1"

    with (
        patch("src.core.api.v1.foundation.donations.public_tenant_scope") as mock_scope,
        patch(
            "src.core.api.v1.foundation.donations.require_hcaptcha", new_callable=AsyncMock
        ) as mock_captcha,
        patch.object(stripe_service, "api_key", "sk" + "_test_wk1"),
        patch("stripe.checkout.Session.create", return_value=mock_session_obj),
    ):
        _patch_tenant_scope(mock_scope, tenant)

        response = await create_donation_checkout(
            tenantSlug="ketikoti-vlaardingen",
            payload=payload,
            request=req,
            session=session,
        )

        assert mock_captcha.called
        assert response["checkout_url"] == "https://checkout.stripe.com/c/pay/cs_test_wk1"
        assert response["session_id"] == "cs_test_wk1"
        assert response["amount_cents"] == 5000
        assert response["frequency"] == "one_time"

        # Donation persisted as pending with the Stripe session id
        assert session.add.called
        added = session.add.call_args.args[0]
        assert isinstance(added, FoundationDonation)
        assert added.status == "pending"
        assert added.stripe_session_id == "cs_test_wk1"
        assert session.commit.await_count >= 1


@pytest.mark.asyncio
async def test_create_donation_checkout_without_stripe_keys_returns_503() -> None:
    """BE-SEC-058: without Stripe keys checkout fails closed with 503.

    No mock checkout session is generated and NO donation row is persisted.
    """
    tenant = _create_mock_tenant()
    req = _create_mock_request()
    session = AsyncMock()

    payload = DonationCheckoutRequest(
        amount_cents=2500,
        frequency="one_time",
        donor_email="donateur@erfgoed.org",
    )

    with (
        patch("src.core.api.v1.foundation.donations.public_tenant_scope") as mock_scope,
        patch("src.core.api.v1.foundation.donations.require_hcaptcha", new_callable=AsyncMock),
        patch.object(stripe_service, "api_key", ""),
    ):
        _patch_tenant_scope(mock_scope, tenant)

        with pytest.raises(HTTPException) as exc_info:
            await create_donation_checkout(
                tenantSlug="ketikoti-vlaardingen",
                payload=payload,
                request=req,
                session=session,
            )

        assert exc_info.value.status_code == 503
        # Fail-closed: nothing persisted, no mock session id anywhere
        assert not session.add.called
        assert session.commit.await_count == 0


# ============================================================================
# Test Webhook Endpoint (BE-SEC-058 fail-closed)
# ============================================================================


def _checkout_completed_payload(session_id: str = "cs_test_wk1") -> bytes:
    return json.dumps(
        {
            "id": "evt_test_wk1",
            "object": "event",
            "type": "checkout.session.completed",
            "livemode": False,
            "data": {
                "object": {
                    "id": session_id,
                    "object": "checkout.session",
                    "payment_intent": "pi_test_wk1",
                    "payment_status": "paid",
                }
            },
        }
    ).encode("utf-8")


@pytest.mark.asyncio
async def test_webhook_without_secret_returns_503_and_no_state_change() -> None:
    """BE-SEC-058: missing webhook secret -> 503; payload is NEVER parsed.

    Regression guard for the fail-open path that parsed the JSON body without
    any signature verification when no whsec was configured.
    """
    payload = _checkout_completed_payload()
    req = _create_mock_request(
        path="/ketikoti-vlaardingen/foundation/donations/webhook",
        headers={"stripe-signature": "t=1,v1=whatever"},
        body=payload,
    )
    session = AsyncMock()

    with patch.object(config, "stripe_webhook_secret", ""):
        with pytest.raises(HTTPException) as exc_info:
            await stripe_donations_webhook(
                tenantSlug="ketikoti-vlaardingen",
                request=req,
                session=session,
            )

    assert exc_info.value.status_code == 503
    # No state change: the donation lookup/update never ran
    assert session.execute.await_count == 0
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_webhook_with_wrong_signature_returns_400_and_no_state_change() -> None:
    """BE-SEC-058: an invalid v1 signature -> 400; nothing is processed."""
    payload = _checkout_completed_payload()
    req = _create_mock_request(
        path="/ketikoti-vlaardingen/foundation/donations/webhook",
        headers={"stripe-signature": "t=1,v1=" + "0" * 64},
        body=payload,
    )
    session = AsyncMock()

    with patch.object(config, "stripe_webhook_secret", TEST_WEBHOOK_SECRET):
        with pytest.raises(HTTPException) as exc_info:
            await stripe_donations_webhook(
                tenantSlug="ketikoti-vlaardingen",
                request=req,
                session=session,
            )

    assert exc_info.value.status_code == 400
    assert session.execute.await_count == 0
    assert session.commit.await_count == 0


@pytest.mark.asyncio
async def test_webhook_without_signature_header_returns_400() -> None:
    """BE-SEC-058: missing Stripe-Signature header -> 400, no state change."""
    payload = _checkout_completed_payload()
    req = _create_mock_request(
        path="/ketikoti-vlaardingen/foundation/donations/webhook",
        body=payload,
    )
    session = AsyncMock()

    with patch.object(config, "stripe_webhook_secret", TEST_WEBHOOK_SECRET):
        with pytest.raises(HTTPException) as exc_info:
            await stripe_donations_webhook(
                tenantSlug="ketikoti-vlaardingen",
                request=req,
                session=session,
            )

    assert exc_info.value.status_code == 400
    assert session.execute.await_count == 0


@pytest.mark.asyncio
async def test_webhook_with_valid_signature_marks_donation_completed() -> None:
    """A correctly self-signed payload (Stripe v1 scheme) is processed.

    The matching pending donation transitions to 'completed'.
    """
    payload = _checkout_completed_payload(session_id="cs_test_signed")
    sig_header = _sign_payload(payload, TEST_WEBHOOK_SECRET)
    req = _create_mock_request(
        path="/ketikoti-vlaardingen/foundation/donations/webhook",
        headers={"stripe-signature": sig_header},
        body=payload,
    )

    tenant = _create_mock_tenant(id=99)
    donation = _make_donation_row(status="pending", stripe_session_id="cs_test_signed")

    session = AsyncMock()
    lookup_result = MagicMock()
    lookup_result.scalar_one_or_none.return_value = donation
    session.execute.return_value = lookup_result

    with (
        patch.object(config, "stripe_webhook_secret", TEST_WEBHOOK_SECRET),
        patch("src.core.api.v1.foundation.donations.public_tenant_scope") as mock_scope,
    ):
        _patch_tenant_scope(mock_scope, tenant)

        response = await stripe_donations_webhook(
            tenantSlug="ketikoti-vlaardingen",
            request=req,
            session=session,
        )

    assert response == {"received": True}
    assert donation.status == "completed"
    assert donation.completed_at is not None
    assert donation.stripe_payment_intent_id == "pi_test_wk1"
    assert session.commit.await_count >= 1


@pytest.mark.asyncio
async def test_webhook_service_never_parses_without_secret() -> None:
    """Direct service-level guard: construct_webhook_event raises instead of parsing."""
    with patch.object(config, "stripe_webhook_secret", ""):
        with pytest.raises(Exception) as exc_info:
            stripe_service.construct_webhook_event(
                b'{"type": "checkout.session.completed"}',
                "t=1,v1=abc",
            )
    assert exc_info.value.__class__.__name__ == "StripeWebhookSecretMissingError"


@pytest.mark.asyncio
async def test_webhook_service_never_parses_with_whitespace_secret() -> None:
    """BE-SEC-056: whitespace-only secret telt niet als geconfigureerd."""
    with patch.object(config, "stripe_webhook_secret", "   "):
        with pytest.raises(Exception) as exc_info:
            stripe_service.construct_webhook_event(
                b'{"type": "checkout.session.completed"}',
                "t=1,v1=abc",
            )
    assert exc_info.value.__class__.__name__ == "StripeWebhookSecretMissingError"


# ============================================================================
# Test Stats & Admin Endpoints
# ============================================================================


@pytest.mark.asyncio
async def test_get_donation_stats_endpoint() -> None:
    """get_donation_stats returns totals from completed donations and masks anonymous donors."""
    tenant = _create_mock_tenant(id=99)
    session = AsyncMock()

    totals_result = MagicMock()
    totals_result.first.return_value = (3500, 2)

    monthly_result = MagicMock()
    monthly_result.scalar.return_value = 1

    public_row = _make_donation_row(
        id=1, amount_cents=1000, donor_name="Publieke Donateur", is_anonymous=False
    )
    anon_row = _make_donation_row(
        id=2,
        amount_cents=2500,
        frequency="monthly",
        donor_name="Geheime Gever",
        is_anonymous=True,
        created_at=datetime(2026, 9, 12, 11, 0, tzinfo=timezone.utc),
    )
    recent_result = MagicMock()
    recent_result.scalars.return_value.all.return_value = [anon_row, public_row]

    session.execute.side_effect = [totals_result, monthly_result, recent_result]

    with patch("src.core.api.v1.foundation.donations.public_tenant_scope") as mock_scope:
        _patch_tenant_scope(mock_scope, tenant)

        stats = await get_donation_stats(
            request=_create_mock_request(path="/ketikoti-vlaardingen/foundation/donations/stats"),
            tenantSlug="ketikoti-vlaardingen",
            session=session,
        )

        assert stats["total_raised_cents"] == 3500
        assert stats["total_donations_count"] == 2
        assert stats["monthly_supporters_count"] == 1
        assert len(stats["recent_donations"]) == 2

        recent = stats["recent_donations"]
        anon_item = next(item for item in recent if item["id"] == 2)
        assert anon_item["donor_name"] == "Anonieme Vriend van het Monument"
        assert anon_item["is_anonymous"] is True

        pub_item = next(item for item in recent if item["id"] == 1)
        assert pub_item["donor_name"] == "Publieke Donateur"


@pytest.mark.asyncio
async def test_list_admin_donations_endpoint() -> None:
    """list_admin_donations provides unmasked email and full audit details to curators."""
    tenant = _create_mock_tenant(id=99)
    curator = _create_mock_curator(tenant_id=99)
    session = AsyncMock()

    rows = [
        _make_donation_row(id=1, email="public@example.org"),
        _make_donation_row(id=2, email="secret@example.org", is_anonymous=True),
    ]
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = rows
    session.execute.return_value = list_result

    with patch("src.core.api.v1.foundation.donations.public_tenant_scope") as mock_scope:
        _patch_tenant_scope(mock_scope, tenant)

        res = await list_admin_donations(
            tenantSlug="ketikoti-vlaardingen",
            current_user=curator,
            session=session,
        )

        assert res["total"] == 2
        emails = [item["donor_email"] for item in res["items"]]
        assert "public@example.org" in emails
        assert "secret@example.org" in emails


@pytest.mark.asyncio
async def test_list_admin_donations_rejects_cross_tenant_curator() -> None:
    """BE-SEC-056: een curator van tenant A krijgt 403 op de admin-lijst van tenant B.

    Rood voor de fix: de endpoint filterte alleen de query op de pad-tenant en
    vergeleek de token-tenant nooit -- donor-e-mails en bedragen van een andere
    tenant waren uitleesbaar met een geldige curator-JWT van een andere tenant.
    """
    tenant = _create_mock_tenant(id=99)
    vreemde_curator = _create_mock_curator(tenant_id=1)
    session = AsyncMock()

    with patch("src.core.api.v1.foundation.donations.public_tenant_scope") as mock_scope:
        _patch_tenant_scope(mock_scope, tenant)

        with pytest.raises(HTTPException) as exc_info:
            await list_admin_donations(
                tenantSlug="ketikoti-vlaardingen",
                current_user=vreemde_curator,
                session=session,
            )

    assert exc_info.value.status_code == 403
    session.execute.assert_not_called()


# ============================================================================
# Test Public Endpoint Registry
# ============================================================================


def test_donations_public_registry_rules() -> None:
    """Verify donations checkout and stats are public, but admin/donations is private."""
    assert PublicEndpointRegistry.is_public("/ketikoti/foundation/donations/checkout") is True
    assert PublicEndpointRegistry.is_public("/ketikoti/foundation/donations/stats") is True
    # Admin route requires authentication and role
    assert PublicEndpointRegistry.is_public("/ketikoti/foundation/admin/donations") is False
