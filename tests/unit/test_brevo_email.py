"""Unit tests for Brevo transactional email connector and service (ADR-029 P1-5)."""

from __future__ import annotations

import unittest.mock as mock
import pytest
import httpx

from src.core.connectors.brevo import (
    BrevoClient,
    BrevoEmailError,
    BrevoEmailProvider,
    mask_email,
)
from src.core.connectors.provider import (
    ProviderCapability,
    ProviderStatus,
)
from src.core.services.brevo_email_service import BrevoEmailService


# ============================================================================
# Email masking / privacy tests
# ============================================================================


def test_mask_email_standard() -> None:
    assert mask_email("user@example.com") == "u***@e***.com"
    assert mask_email("john.doe@sub.domain.org") == "j***@s***.domain.org"


def test_mask_email_edge_cases() -> None:
    assert mask_email("") == "***"
    assert mask_email("invalid-email") == "***"
    assert mask_email("a@b.c") == "a***@b***.c"


# ============================================================================
# BrevoClient simulated / dev mode tests
# ============================================================================


@pytest.mark.asyncio
async def test_brevo_client_simulated_mode() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    assert not client.is_live

    client.clear_sent_emails()
    res = await client.send_email(
        to_email="visitor@example.com",
        subject="Test Onderwerp",
        html_content="<p>Test</p>",
        text_content="Test",
    )

    assert "messageId" in res
    assert res["messageId"].startswith("mock_brevo_")
    assert len(client.sent_emails) == 1
    assert client.sent_emails[0]["to_email"] == "visitor@example.com"
    assert client.sent_emails[0]["subject"] == "Test Onderwerp"

    client.clear_sent_emails()
    assert len(client.sent_emails) == 0

    health = await client.health_check()
    assert health.status == ProviderStatus.HEALTHY


# ============================================================================
# BrevoClient live API tests (with mocked httpx)
# ============================================================================


@pytest.mark.asyncio
async def test_brevo_client_live_success() -> None:
    client = BrevoClient(api_key="xkeysib-prod-api-key-9999999999")
    assert client.is_live

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"messageId": "<20260911.msg123@smtp-relay.brevo.com>"}

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        res = await client.send_email(
            to_email="test@domain.nl",
            subject="Welkom",
            html_content="<h1>Hallo</h1>",
            text_content="Hallo",
            tags=["welcome"],
            reply_to="support@domain.nl",
        )

        assert res["messageId"] == "<20260911.msg123@smtp-relay.brevo.com>"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["headers"]["api-key"] == "xkeysib-prod-api-key-9999999999"
        assert kwargs["json"]["to"][0]["email"] == "test@domain.nl"
        assert kwargs["json"]["tags"] == ["welcome"]
        assert kwargs["json"]["replyTo"]["email"] == "support@domain.nl"


@pytest.mark.asyncio
async def test_brevo_client_live_api_error() -> None:
    client = BrevoClient(api_key="xkeysib-prod-api-key-9999999999")

    mock_resp = mock.MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Key not found"

    with mock.patch("httpx.AsyncClient.post", new_callable=mock.AsyncMock) as mock_post:
        mock_post.return_value = mock_resp

        with pytest.raises(BrevoEmailError) as exc_info:
            await client.send_email(
                to_email="test@domain.nl",
                subject="Error test",
                html_content="<p>Error</p>",
            )
        assert exc_info.value.status_code == 401
        assert "Key not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_brevo_client_live_network_error() -> None:
    client = BrevoClient(api_key="xkeysib-prod-api-key-9999999999")

    with mock.patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(BrevoEmailError) as exc_info:
            await client.send_email(
                to_email="test@domain.nl",
                subject="Net error",
                html_content="<p>Net</p>",
            )
        assert "Brevo network connection failed" in str(exc_info.value)


@pytest.mark.asyncio
async def test_brevo_client_live_health_check() -> None:
    client = BrevoClient(api_key="xkeysib-prod-api-key-9999999999")

    # Healthy
    mock_resp_ok = mock.MagicMock()
    mock_resp_ok.status_code = 200
    with mock.patch(
        "httpx.AsyncClient.get", new_callable=mock.AsyncMock, return_value=mock_resp_ok
    ):
        health = await client.health_check()
        assert health.status == ProviderStatus.HEALTHY

    # Degraded
    mock_resp_err = mock.MagicMock()
    mock_resp_err.status_code = 503
    with mock.patch(
        "httpx.AsyncClient.get", new_callable=mock.AsyncMock, return_value=mock_resp_err
    ):
        health = await client.health_check()
        assert health.status == ProviderStatus.DEGRADED

    # Unavailable (network exception)
    with mock.patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("Timeout")):
        health = await client.health_check()
        assert health.status == ProviderStatus.UNAVAILABLE


# ============================================================================
# BrevoEmailProvider tests
# ============================================================================


@pytest.mark.asyncio
async def test_brevo_email_provider() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    provider = BrevoEmailProvider(client=client)

    # Valid execution
    res = await provider.execute(
        capability=ProviderCapability.EMAIL_SEND,
        payload={
            "to": "curator@example.com",
            "subject": "Review vereist",
            "html_body": "<p>Graag nakijken</p>",
        },
    )
    assert res.success
    assert res.provider_id == "brevo"
    assert "messageId" in (res.data or {})

    # Unsupported capability
    res_unsupported = await provider.execute(
        capability=ProviderCapability.SMS_SEND,
        payload={"to": "+31612345678", "body": "test"},
    )
    assert not res_unsupported.success
    assert res_unsupported.error_code == "UNSUPPORTED_CAPABILITY"

    # Missing fields
    res_invalid = await provider.execute(
        capability=ProviderCapability.EMAIL_SEND,
        payload={"body": "Missing to and subject"},
    )
    assert not res_invalid.success
    assert res_invalid.error_code == "INVALID_PAYLOAD"


# ============================================================================
# BrevoEmailService high-level methods tests
# ============================================================================


@pytest.mark.asyncio
async def test_brevo_email_service_magic_link() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    service = BrevoEmailService(client=client)
    service.clear_sent_emails()

    success = await service.send_magic_link(
        to_email="visitor@monument.nl",
        magic_link_url="https://monument.nl/auth/verify?token=abc123token",
        expires_in_minutes=15,
        tenant_name="Levend Monument Zeeland",
    )

    assert success
    assert len(service.sent_emails) == 1
    sent = service.sent_emails[0]
    assert sent["to_email"] == "visitor@monument.nl"
    assert "Levend Monument Zeeland" in sent["subject"]
    assert "https://monument.nl/auth/verify?token=abc123token" in sent["html_content"]
    assert "15 minuten" in sent["html_content"]
    assert "magic-link" in sent["tags"]


@pytest.mark.asyncio
async def test_brevo_email_service_takedown() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    service = BrevoEmailService(client=client)
    service.clear_sent_emails()

    success = await service.send_takedown_confirmation(
        to_email="reporter@rechten.nl",
        takedown_id=987,
        content_title="Oorlogsdagboek 1944",
        tenant_name="Het Levend Monument",
    )

    assert success
    assert len(service.sent_emails) == 1
    sent = service.sent_emails[0]
    assert sent["to_email"] == "reporter@rechten.nl"
    assert "#987" in sent["subject"]
    assert "Oorlogsdagboek 1944" in sent["html_content"]
    assert "Notice and Take Down" in sent["html_content"]


@pytest.mark.asyncio
async def test_brevo_email_service_newsletter() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    service = BrevoEmailService(client=client)
    service.clear_sent_emails()

    success = await service.send_newsletter_confirmation(
        to_email="subscriber@historie.nl",
        unsubscribe_url="https://monument.nl/newsletter/unsubscribe?token=unsub123",
        tenant_name="Het Levend Monument",
    )

    assert success
    assert len(service.sent_emails) == 1
    sent = service.sent_emails[0]
    assert sent["to_email"] == "subscriber@historie.nl"
    assert "Welkom bij de nieuwsbrief" in sent["subject"]
    assert "token=unsub123" in sent["html_content"]


@pytest.mark.asyncio
async def test_brevo_email_service_newsletter_optin() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    service = BrevoEmailService(client=client)
    service.clear_sent_emails()

    success = await service.send_newsletter_optin_request(
        to_email="optin@historie.nl",
        confirm_url="https://monument.nl/default/foundation/newsletter/confirm?email=optin@historie.nl&token=sec123",
        tenant_name="Het Levend Monument",
    )

    assert success
    assert len(service.sent_emails) == 1
    sent = service.sent_emails[0]
    assert sent["to_email"] == "optin@historie.nl"
    assert "Bevestig uw inschrijving" in sent["subject"]
    assert "token=sec123" in sent["html_content"]
    assert "double-opt-in" in sent["tags"]


@pytest.mark.asyncio
async def test_brevo_email_service_contact_confirmation() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    service = BrevoEmailService(client=client)
    service.clear_sent_emails()

    success = await service.send_contact_confirmation(
        to_email="indiener@voorbeeld.nl",
        reference_id="CON-20260914-ABCD",
        sender_name="Klaas Vaak",
        subject="Vraag over collectie",
        tenant_name="Levend Monument",
    )

    assert success
    assert len(service.sent_emails) == 1
    sent = service.sent_emails[0]
    assert sent["to_email"] == "indiener@voorbeeld.nl"
    assert "CON-20260914-ABCD" in sent["subject"]
    assert "Klaas Vaak" in sent["html_content"]
    assert "portal-contact" in sent["tags"]


@pytest.mark.asyncio
async def test_brevo_email_service_contact_notification() -> None:
    client = BrevoClient(api_key="test_dummy_key_12345")
    service = BrevoEmailService(client=client)
    service.clear_sent_emails()

    success = await service.send_contact_notification(
        to_email="beheer@stichting.nl",
        reference_id="CON-20260914-EF01",
        sender_name="Maaike Jansen",
        sender_email="maaike@school.nl",
        subject="Aanvraag gastles",
        category="educatie",
        message="Graag willen we met klas 3 langskomen.",
        tenant_name="Levend Monument",
    )

    assert success
    assert len(service.sent_emails) == 1
    sent = service.sent_emails[0]
    assert sent["to_email"] == "beheer@stichting.nl"
    assert "Aanvraag gastles" in sent["subject"]
    assert "EDUCATIE" in sent["subject"]
    assert "maaike@school.nl" in sent["html_content"]
    assert "Graag willen we met klas 3 langskomen." in sent["html_content"]
    assert "portal-contact" in sent["tags"]

