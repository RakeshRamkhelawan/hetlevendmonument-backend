"""Brevo (Sendinblue) Transactional Email Connector (ADR-029 P1-5).

Provides:
- BrevoClient: Direct async HTTP client for Brevo REST API v3 (/smtp/email).
- BrevoEmailProvider: Provider abstraction conforming to Provider base class.
- Dev/Test simulation mode with in-memory recording and PII masking.
"""

from __future__ import annotations

import logging
import os
import time
import uuid

import httpx

from src.core.connectors.provider import (
    Provider,
    ProviderCapability,
    ProviderHealth,
    ProviderResult,
    ProviderStatus,
)
from src.core.shared.config import get_settings

logger = logging.getLogger(__name__)


def mask_email(email: str) -> str:
    """Mask email for privacy in audit logs (e.g. user@example.com -> u***@e***.com)."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    masked_local = (local[0] + "***") if len(local) > 0 else "***"
    domain_parts = domain.split(".", 1)
    if len(domain_parts) == 2:
        masked_domain = domain_parts[0][0] + "***." + domain_parts[1]
    else:
        masked_domain = domain[0] + "***" if domain else "***"
    return f"{masked_local}@{masked_domain}"


class BrevoEmailError(Exception):
    """Raised when Brevo email sending fails."""

    def __init__(
        self, message: str, status_code: int | None = None, response_body: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class BrevoClient:
    """Async HTTP client for Brevo transactional email API v3."""

    def __init__(
        self,
        api_key: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        base_url: str = "https://api.brevo.com/v3",
        timeout: float = 10.0,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or os.getenv("BREVO_API_KEY") or settings.brevo_api_key
        self.sender_email = (
            sender_email
            or os.getenv("BREVO_SENDER_EMAIL")
            or settings.brevo_sender_email
            or "noreply@sanskritisetu.org"
        )
        self.sender_name = (
            sender_name
            or os.getenv("BREVO_SENDER_NAME")
            or settings.brevo_sender_name
            or "Het Levend Monument"
        )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._sent_emails: list[dict[str, object]] = []

    @property
    def is_live(self) -> bool:
        """Check if client has a valid production API key configured."""
        if not self.api_key:
            return False
        clean = self.api_key.strip().lower()
        return not (
            clean.startswith(("test", "dummy", "mock")) or clean == "none" or len(clean) < 10
        )

    @property
    def sent_emails(self) -> list[dict[str, object]]:
        """Return recorded emails sent in simulated/test mode."""
        return self._sent_emails

    def clear_sent_emails(self) -> None:
        """Clear recorded emails (for test isolation)."""
        self._sent_emails.clear()

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        to_name: str | None = None,
        tags: list[str] | None = None,
        reply_to: str | None = None,
    ) -> dict[str, object]:
        """Send a transactional email via Brevo REST API v3.

        In test/dev mode without live credentials, simulates sending and
        stores email in memory.
        """
        masked = mask_email(to_email)

        if not self.is_live:
            msg_id = f"mock_brevo_{uuid.uuid4().hex[:16]}"
            record: dict[str, object] = {
                "message_id": msg_id,
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
                "text_content": text_content,
                "tags": tags or [],
                "sent_at": time.time(),
            }
            self._sent_emails.append(record)
            logger.info(
                "brevo_email_simulated: to=%s subject=%s message_id=%s", masked, subject, msg_id
            )
            return {"messageId": msg_id}

        payload: dict[str, object] = {
            "sender": {"name": self.sender_name, "email": self.sender_email},
            "to": [{"email": to_email, "name": to_name or to_email.split("@")[0]}],
            "subject": subject,
            "htmlContent": html_content,
        }
        if text_content:
            payload["textContent"] = text_content
        if tags:
            payload["tags"] = tags
        if reply_to:
            payload["replyTo"] = {"email": reply_to}

        headers = {
            "api-key": self.api_key or "",
            "accept": "application/json",
            "content-type": "application/json",
        }

        url = f"{self.base_url}/smtp/email"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
        except Exception as exc:
            logger.error("brevo_send_error: to=%s error=%s", masked, str(exc))
            raise BrevoEmailError(f"Brevo network connection failed: {exc}") from exc

        if response.status_code in (200, 201):
            data: dict[str, object] = response.json()
            logger.info("brevo_email_sent: to=%s message_id=%s", masked, data.get("messageId"))
            return data

        logger.error(
            "brevo_api_failed: to=%s status=%d body=%s",
            masked,
            response.status_code,
            response.text[:200],
        )
        raise BrevoEmailError(
            f"Brevo API error {response.status_code}: {response.text}",
            status_code=response.status_code,
            response_body=response.text,
        )

    async def health_check(self) -> ProviderHealth:
        """Check connection health with Brevo API."""
        if not self.is_live:
            return ProviderHealth(
                provider_id="brevo",
                status=ProviderStatus.HEALTHY,
                last_error_message=None,
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/account",
                    headers={"api-key": self.api_key or "", "accept": "application/json"},
                )
            if response.status_code == 200:
                return ProviderHealth(
                    provider_id="brevo",
                    status=ProviderStatus.HEALTHY,
                )
            return ProviderHealth(
                provider_id="brevo",
                status=ProviderStatus.DEGRADED,
                last_error_message=f"Brevo HTTP {response.status_code}",
            )
        except Exception as exc:
            return ProviderHealth(
                provider_id="brevo",
                status=ProviderStatus.UNAVAILABLE,
                last_error_message=str(exc),
            )


class BrevoEmailProvider(Provider):
    """Brevo provider implementation for connector framework."""

    def __init__(
        self,
        client: BrevoClient | None = None,
        provider_id: str = "brevo",
        config: dict[str, object] | None = None,
    ) -> None:
        super().__init__(
            provider_id=provider_id,
            capabilities=[ProviderCapability.EMAIL_SEND],
            config=config,
        )
        self.client = client or BrevoClient()

    async def execute(
        self,
        capability: ProviderCapability,
        payload: dict[str, object],
        timeout_ms: int = 30000,
    ) -> ProviderResult:
        """Execute email send via Brevo."""
        start_time = time.perf_counter()

        if capability != ProviderCapability.EMAIL_SEND:
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                error_message=f"Unsupported capability: {capability}",
                error_code="UNSUPPORTED_CAPABILITY",
            )

        raw_to = payload.get("to") or payload.get("recipient")
        to_email = str(raw_to) if raw_to is not None else ""
        raw_subject = payload.get("subject", "")
        subject = str(raw_subject) if raw_subject is not None else ""
        raw_html = (
            payload.get("html_body") or payload.get("body_html") or payload.get("body", "")
        )
        html_content = str(raw_html) if raw_html is not None else ""
        raw_body = payload.get("body")
        text_content = str(raw_body) if raw_body is not None else None
        raw_name = payload.get("to_name")
        to_name = str(raw_name) if raw_name is not None else None

        if not to_email or not subject:
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                error_message="Missing required email fields (to, subject)",
                error_code="INVALID_PAYLOAD",
            )

        try:
            result = await self.client.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                to_name=to_name,
            )
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.record_request(success=True, latency_ms=latency_ms)
            return ProviderResult(
                success=True,
                provider_id=self.provider_id,
                data=result,
                latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.record_request(success=False, latency_ms=latency_ms)
            return ProviderResult(
                success=False,
                provider_id=self.provider_id,
                error_message=str(exc),
                error_code="BREVO_SEND_FAILED",
                latency_ms=latency_ms,
            )

    async def health_check(self) -> ProviderHealth:
        """Check Brevo provider health."""
        health = await self.client.health_check()
        self.update_health(health)
        return health
