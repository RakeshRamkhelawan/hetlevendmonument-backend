"""
Email Executor for Workflow Integration
========================================

Real SMTP email integration replacing mock executor.

Features:
- Send plain text emails
- Send HTML emails
- Support for multiple recipients
- SMTP authentication
"""

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

logger = logging.getLogger(__name__)


class EmailExecutor:
    """
    Production email executor for workflows.

    Requires environment variables:
        SMTP_HOST: smtp.gmail.com
        SMTP_PORT: 587
        SMTP_USER: your-email@gmail.com
        SMTP_PASSWORD: your-app-password
        EMAIL_FROM: noreply@sanskritisetu.org

    Usage in workflow node:
        {
            "type": "email_agent",
            "config": {
                "to": ["user@example.com"],
                "cc": ["manager@example.com"],
                "subject": "Subject line",
                "body": "Plain text body",
                "html_body": "<h1>HTML body</h1>"
            }
        }
    """

    def __init__(self) -> None:
        """Initialize email executor with SMTP configuration."""
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user: str | None = os.getenv("SMTP_USER")
        self.smtp_password: str | None = os.getenv("SMTP_PASSWORD")
        self.from_email: str | None = os.getenv("EMAIL_FROM", self.smtp_user)

        if not self.smtp_user or not self.smtp_password:
            logger.warning("SMTP credentials not set. Email executor will fail.")

    async def execute(self, node: dict[str, Any], context: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Execute email send action.

        Args:
            node: Node configuration with 'config' field
            context: Execution context (not used currently)

        Returns:
            Result dictionary with success status
        """
        if not self.smtp_user or not self.smtp_password:
            return {
                "success": False,
                "error": "SMTP credentials not set. Check SMTP_USER and SMTP_PASSWORD.",
            }

        config = node.get("config", {})

        try:
            return await self._send_email(config)
        except Exception as exc:
            logger.exception("email_executor_error: %s", exc)
            return {"success": False, "error": str(exc)}

    async def _send_email(self, config: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Send email via SMTP."""
        to: list[str] = config.get("to", [])
        cc: list[str] = config.get("cc", [])
        subject: str = config.get("subject", "(No Subject)")
        body: str | None = config.get("body")
        html_body: str | None = config.get("html_body")

        if not to:
            return {"success": False, "error": "Missing required field: to"}

        if not isinstance(to, list):
            to = [to]

        if cc and not isinstance(cc, list):
            cc = [cc]

        # Extra None check voor type safety (na de check in execute)
        if self.smtp_user is None or self.smtp_password is None:
            return {
                "success": False,
                "error": "SMTP credentials not set. Check SMTP_USER and SMTP_PASSWORD.",
            }

        # Lokale variabelen voor type narrowing
        smtp_user: str = self.smtp_user
        smtp_password: str = self.smtp_password
        from_email: str = self.from_email or smtp_user

        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = ", ".join(to)

        if cc:
            msg["Cc"] = ", ".join(cc)

        # Attach plain text body
        if body:
            msg.attach(MIMEText(body, "plain"))

        # Attach HTML body
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        # Send email
        all_recipients = to + (cc or [])

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)

            logger.info("email_dispatch_success: executor=true")

            return {
                "success": True,
                "sent_to": to,
                "cc": cc,
                "subject": subject,
                "from": from_email,
            }

        except smtplib.SMTPAuthenticationError as exc:
            logger.error("smtp_auth_failed: %s", exc)
            return {
                "success": False,
                "error_type": "authentication_failed",
                "error": "SMTP authentication failed. Check credentials.",
            }
        except smtplib.SMTPException as exc:
            logger.error("smtp_error: %s", exc)
            return {"success": False, "error_type": "smtp_error", "error": str(exc)}
        except Exception as exc:
            logger.exception("email_send_error: %s", exc)
            return {"success": False, "error_type": "unknown_error", "error": str(exc)}


# Factory function for executor registry
def create_email_executor() -> EmailExecutor:
    """Create email executor instance."""
    return EmailExecutor()
