"""
Unit Tests for Email Service (SC-5.2)

Tests email service interface and implementations.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.core.services.email import (
    ConsoleEmailService,
    EmailMessage,
    EmailServiceInterface,
    SMTPEmailService,
    get_email_service,
)


class TestEmailMessage:
    """Tests for EmailMessage data class."""

    def test_basic_message(self):
        """Test creating a basic email message."""
        msg = EmailMessage(to="test@example.com", subject="Test Subject", body="Test body")
        assert msg.to == "test@example.com"
        assert msg.subject == "Test Subject"
        assert msg.body == "Test body"
        assert msg.html_body is None

    def test_message_with_html(self):
        """Test email message with HTML body."""
        msg = EmailMessage(
            to="test@example.com",
            subject="Test",
            body="Plain text",
            html_body="<h1>HTML</h1>",
        )
        assert msg.html_body == "<h1>HTML</h1>"

    def test_message_with_list_recipients(self):
        """Test email with multiple recipients."""
        msg = EmailMessage(
            to=["user1@example.com", "user2@example.com"], subject="Test", body="Body"
        )
        assert len(msg.to) == 2


class TestConsoleEmailService:
    """Tests for ConsoleEmailService."""

    @pytest.mark.asyncio
    async def test_send_returns_true(self):
        """Test that console service always returns True."""
        service = ConsoleEmailService()
        msg = EmailMessage(to="test@example.com", subject="Test", body="Body")
        result = await service.send(msg)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_template_returns_true(self):
        """Test that template sending returns True."""
        service = ConsoleEmailService()
        result = await service.send_template(
            to="test@example.com", template_name="welcome", context={"name": "John"}
        )
        assert result is True


class TestSMTPEmailService:
    """Tests for SMTPEmailService."""

    def test_default_configuration(self):
        """Test default SMTP configuration.

        `patch.dict(clear=True)` wist ook `TESTING`; zonder die variabele leest de mailkeuze de
        app-configuratie (`UnifiedConfig`, gecachet per proces en gevuld uit `.env`). Gemeten
        2026-10-16: met een gecachte configuratie die een mailhost heeft gaf deze test
        'smtp.mailgun.org' in plaats van 'localhost' (testpoort, 1 rood van 25151). De test
        bedoelt "niets ingesteld", dus de configuratie wordt hier leeg gezet.
        """
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("src.core.services.email._smtp_uit_configuratie", return_value=(None, None)),
        ):
            service = SMTPEmailService()
            assert service.host == "localhost"
            assert service.port == 587
            assert service.use_tls is True

    def test_custom_configuration(self):
        """Test custom SMTP configuration."""
        service = SMTPEmailService(
            host="smtp.example.com",
            port=465,
            username="user",
            password="pass",
            use_tls=False,
        )
        assert service.host == "smtp.example.com"
        assert service.port == 465


class TestGetEmailService:
    """Tests for email service factory."""

    def test_development_returns_console(self, monkeypatch):
        """Test development environment returns console service."""
        # Voorwaarde van deze test: geen SMTP_HOST (anders kiest de factory SMTP).
        monkeypatch.delenv("SMTP_HOST", raising=False)
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}):
            # Clear cache
            get_email_service.cache_clear() if hasattr(get_email_service, "cache_clear") else None
            service = get_email_service()
            assert isinstance(service, ConsoleEmailService)

    def test_production_returns_smtp(self):
        """Test production environment returns SMTP service."""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}):
            service = get_email_service()
            assert isinstance(service, SMTPEmailService)
