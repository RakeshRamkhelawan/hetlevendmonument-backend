"""
SP-E01: Password reset echte e-mail verzenden.

Tests:
- send_password_reset_email bestaat en is callable
- Auth router roept email service aan (niet logger.info met token)
- Geen PII (email, token) in logs
- Graceful fallback als SMTP niet geconfigureerd
- FRONTEND_URL env var gebruikt voor reset URL
"""

import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

_AUTH_ROUTER_PATH = Path(__file__).resolve().parents[2] / "src/core/api/auth/router_password.py"

import pytest


@pytest.fixture(autouse=True)
def reset_password_rate_limiter() -> None:
    """Reset password-router rate limiter storage so other suites don't 429 us."""
    from src.core.api.auth.router_password import auth_limiter

    storage = getattr(auth_limiter, "_storage", None)
    if storage is not None:
        if hasattr(storage, "reset"):
            storage.reset()
        elif hasattr(storage, "clear"):
            storage.clear()
    yield


class TestSendPasswordResetEmailExists:
    """Email service heeft send_password_reset_email functie."""

    def test_function_exists(self):
        """send_password_reset_email is importeerbaar en callable."""
        from src.core.services.email import send_password_reset_email

        assert callable(send_password_reset_email)

    @pytest.mark.asyncio
    async def test_function_is_async(self):
        """send_password_reset_email is een async functie."""
        import inspect
        from src.core.services.email import send_password_reset_email

        assert inspect.iscoroutinefunction(send_password_reset_email)


class TestSendPasswordResetEmailBehavior:
    """Gedrag van send_password_reset_email."""

    @pytest.mark.asyncio
    async def test_sends_email_via_service(self):
        """Functie gebruikt email service om email te versturen."""
        from src.core.services.email import send_password_reset_email

        with patch("src.core.services.email.get_email_service") as mock_get:
            mock_service = AsyncMock()
            mock_get.return_value = mock_service

            await send_password_reset_email(
                "user@example.com", "https://app.sanskritisetu.org/reset?token=abc123"
            )

            mock_get.assert_called_once()
            mock_service.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_password_reset_template(self):
        """Functie gebruikt password_reset template."""
        from src.core.services.email import send_password_reset_email

        with patch("src.core.services.email.get_email_service") as mock_get:
            mock_service = AsyncMock()
            mock_get.return_value = mock_service

            await send_password_reset_email(
                "user@example.com", "https://app.sanskritisetu.org/reset?token=abc123"
            )

            call_args = mock_service.send.call_args[0][0]
            # Het onderwerp gaat over het wachtwoord, in het Nederlands (de klant ziet geen Engelse mail).
            assert "wachtwoord" in call_args.subject.lower()
            # Body (text or html) moet de reset URL bevatten
            body_combined = (call_args.body or "") + (call_args.html_body or "")
            assert "https://app.sanskritisetu.org/reset?token=abc123" in body_combined

    @pytest.mark.asyncio
    async def test_graceful_when_smtp_not_configured(self):
        """Bij ontbrekende SMTP config: warning log, geen exception."""
        from src.core.services.email import send_password_reset_email

        with patch.dict("os.environ", {"SMTP_HOST": ""}, clear=False):
            with patch("src.core.services.email.get_email_service") as mock_get:
                mock_service = AsyncMock()
                mock_service.send.return_value = True
                mock_get.return_value = mock_service

                await send_password_reset_email(
                    "user@example.com", "https://app.sanskritisetu.org/reset?token=abc123"
                )
                # Geen exception = success

    @pytest.mark.asyncio
    async def test_does_not_log_email_address(self, caplog):
        """Functie logt geen e-mailadres (PII)."""
        from src.core.services.email import send_password_reset_email

        with caplog.at_level(logging.INFO):
            with patch("src.core.services.email.get_email_service") as mock_get:
                mock_service = AsyncMock()
                mock_service.send.return_value = True
                mock_get.return_value = mock_service

                await send_password_reset_email(
                    "secret@example.com", "https://app.sanskritisetu.org/reset?token=abc123"
                )

        for record in caplog.records:
            assert "secret@example.com" not in record.message
            assert "secret" not in record.message

    @pytest.mark.asyncio
    async def test_does_not_log_reset_token(self, caplog):
        """Functie logt geen reset-token."""
        from src.core.services.email import send_password_reset_email

        with caplog.at_level(logging.DEBUG):
            with patch("src.core.services.email.get_email_service") as mock_get:
                mock_service = AsyncMock()
                mock_service.send.return_value = True
                mock_get.return_value = mock_service

                await send_password_reset_email(
                    "user@example.com",
                    "https://app.sanskritisetu.org/reset?token=supersecrettoken123",
                )

        for record in caplog.records:
            assert "supersecrettoken123" not in record.message


class TestAuthRouterNoPII:
    """Auth router logt geen PII en roept email service aan."""

    def test_todo_comment_removed(self):
        """TODO comment voor email is verwijderd."""
        source = _AUTH_ROUTER_PATH.read_text(encoding="utf-8")
        assert "TODO: Send email with reset link" not in source

    def test_no_token_logging_in_forgot_password(self):
        """forgot_password logt geen token of emailadres."""
        source = _AUTH_ROUTER_PATH.read_text(encoding="utf-8")
        assert "In production, this would be sent to" not in source
        assert 'f"Password reset token generated for user' not in source

    def test_calls_send_password_reset_email(self):
        """forgot_password roept send_password_reset_email aan."""
        source = _AUTH_ROUTER_PATH.read_text(encoding="utf-8")
        assert "send_password_reset_email" in source

    def test_uses_frontend_url_env_var(self, monkeypatch):
        """Reset-URL wordt opgebouwd vanuit FRONTEND_URL env var.

        Was een zoektekst in de broncode; sinds de link via `frontend_url()` loopt (workflowscherm nazorg, punt 3) toetst dit
        het GEDRAG: de ingestelde URL staat in de link.
        """
        from src.core.api.auth.router_password import _reset_url

        monkeypatch.setenv("FRONTEND_URL", "https://app.example.org")

        assert _reset_url("tok") == "https://app.example.org/reset-password?token=tok"


class TestEmailServiceNoPII:
    """Email service logt geen PII bij succes of falen."""

    def test_smtp_service_does_not_log_recipient(self):
        """SMTPEmailService.send logt geen recipient email."""
        import inspect
        from src.core.services.email import SMTPEmailService

        source = inspect.getsource(SMTPEmailService.send)
        # Check dat er geen f-string is met message.to
        assert 'f"Email sent to {message.to}' not in source

    def test_console_service_does_not_log_recipient(self):
        """ConsoleEmailService.send logt geen recipient email."""
        import inspect
        from src.core.services.email import ConsoleEmailService

        source = inspect.getsource(ConsoleEmailService.send)
        assert 'f"To: {message.to}"' not in source
        assert 'logger.info(f"To:' not in source


class TestAuthForgotPasswordEndpoint:
    """Endpoint-level tests voor forgot-password."""

    @pytest.mark.asyncio
    async def test_forgot_password_calls_email_service(self, test_client, test_user):
        """POST /auth/forgot-password roept email service aan voor bestaande user."""
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock(return_value=True)
        with (
            patch(
                "src.core.api.auth.router_password.get_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
            patch("src.core.api.auth.router_password.send_password_reset_email") as mock_send,
        ):
            response = await test_client.post(
                "/api/v1/auth/forgot-password",
                json={"email": test_user["email"]},
            )
            assert response.status_code == 200

            # Hier stond een wachtlus van honderd keer 10ms "tot de fire-and-forget taak echt
            # heeft gelopen". Die lus kon per constructie niets doen en is weggehaald
            # (ADR-036 OP-131).
            #
            # `patch()` maakt van een `async def` een AsyncMock, en `call_count` loopt op bij de
            # AANROEP -- niet bij het await'en. `asyncio.create_task(send_password_reset_email(...))`
            # roept de functie synchroon aan om de coroutine te maken die het daarna inplant. Op het
            # moment dat het endpoint antwoordt staat de teller dus al op 1; wachten voegt niets toe.
            # Nagemeten: aanroepen zonder await geeft direct call_count == 1.
            #
            # Dat maakt de diagnose van 2026-08-02 onjuist. Deze test viel niet om door een trage
            # scheduler maar doordat de globale tenantfilter actief was in die xdist-worker: zonder
            # tenantcontext krijgt de user-lookup `WHERE false` mee, wordt er geen gebruiker
            # gevonden en start de taak nooit. De echte fix zit in `router_password.py`
            # (`TenantFilterBypass`); de productie-eigenschap wordt bewaakt door
            # `tests/unit/test_auth_endpoints_survive_the_tenant_filter.py`, die de filter
            # expliciet aanzet in plaats van te hopen dat hij uit staat.
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_forgot_password_never_reveals_user_existence(self, test_client, test_user):
        """Endpoint geeft identieke response voor bekend en onbekend email."""
        response_known = await test_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": test_user["email"]},
        )
        response_unknown = await test_client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "unknown_random_xyz@example.com"},
        )

        assert response_known.status_code == response_unknown.status_code == 200
        assert response_known.json() == response_unknown.json()
