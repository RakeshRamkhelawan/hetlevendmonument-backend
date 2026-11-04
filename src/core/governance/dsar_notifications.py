"""
DSAR Notification Service

Handles email notifications for Data Subject Access Request (DSAR) operations.
Uses the email service interface for sending privacy-related notifications.

Usage:
    from src.core.governance.dsar_notifications import DSARNotificationService

    service = DSARNotificationService(email_service)
    await service.notify_export_ready(user, download_url, expiry_date)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.services.email import EmailMessage, EmailServiceInterface

logger = logging.getLogger(__name__)


@dataclass
class ExportNotificationContext:
    """Context data for export ready notification."""

    user_name: str
    user_email: str
    requested_at: datetime
    export_format: str
    download_url: str
    expiry_date: datetime
    categories: dict[str, bool]
    privacy_portal_url: str = "https://app.sanskritisetu.org/settings/privacy"
    privacy_policy_url: str = "https://sanskritisetu.org/privacy-policy"
    terms_url: str = "https://sanskritisetu.org/terms"


@dataclass
class DeletionNotificationContext:
    """Context data for account deletion confirmation."""

    user_name: str
    user_email: str
    processed_at: datetime
    deletion_type: str  # "Soft Delete" or "Hard Delete"
    grace_period_end: datetime | None = None
    restore_url: str | None = None
    feedback_url: str = "https://sanskritisetu.org/feedback"
    privacy_policy_url: str = "https://sanskritisetu.org/privacy-policy"
    gdpr_rights_url: str = "https://sanskritisetu.org/gdpr-rights"


class DSARNotificationService:
    """Service for sending DSAR-related email notifications."""

    def __init__(self, email_service: EmailServiceInterface) -> None:
        """
        Initialize the notification service.

        Args:
            email_service: The email service to use for sending emails
        """
        self.email_service = email_service

    async def notify_export_ready(
        self,
        context: ExportNotificationContext,
    ) -> bool:
        """
        Send email notification that data export is ready.

        Args:
            context: Export notification context with all required data

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Calculate expiry days
            expiry_days = (context.expiry_date - datetime.now(timezone.utc)).days

            email_context = {
                "user_name": context.user_name,
                "requested_at": context.requested_at.strftime("%d %B %Y, %H:%M"),
                "export_format": context.export_format.upper(),
                "download_url": context.download_url,
                "expiry_date": context.expiry_date.strftime("%d %B %Y, %H:%M"),
                "expiry_days": max(0, expiry_days),
                "categories": context.categories,
                "privacy_portal_url": context.privacy_portal_url,
                "privacy_policy_url": context.privacy_policy_url,
                "terms_url": context.terms_url,
            }

            success = await self.email_service.send_template(
                to=context.user_email,
                template_name="dsar_export_ready",
                context=email_context,
            )

            if success:
                logger.info(f"Export ready notification sent to {context.user_email}")
            else:
                logger.error(f"Failed to send export notification to {context.user_email}")

            return success

        except Exception as e:
            logger.exception(f"Error sending export notification: {e}")
            return False

    async def notify_account_deleted(
        self,
        context: DeletionNotificationContext,
    ) -> bool:
        """
        Send email confirmation for account deletion.

        Args:
            context: Deletion notification context with all required data

        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            email_context: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
                "user_name": context.user_name,
                "processed_at": context.processed_at.strftime("%d %B %Y, %H:%M"),
                "deletion_type": context.deletion_type,
                "feedback_url": context.feedback_url,
                "privacy_policy_url": context.privacy_policy_url,
                "gdpr_rights_url": context.gdpr_rights_url,
            }

            # Add grace period info for soft deletes
            if context.deletion_type == "Soft Delete" and context.grace_period_end:
                email_context["grace_period_end"] = context.grace_period_end.strftime(
                    "%d %B %Y, %H:%M"
                )
                email_context["restore_url"] = context.restore_url or ""
            else:
                email_context["grace_period_end"] = None
                email_context["restore_url"] = None

            success = await self.email_service.send_template(
                to=context.user_email,
                template_name="account_deleted_confirmation",
                context=email_context,
            )

            if success:
                logger.info(f"Deletion confirmation sent to {context.user_email}")
            else:
                logger.error(f"Failed to send deletion confirmation to {context.user_email}")

            return success

        except Exception as e:
            logger.exception(f"Error sending deletion confirmation: {e}")
            return False

    async def notify_export_requested(
        self,
        user_email: str,
        user_name: str,
        estimated_completion: datetime,
    ) -> bool:
        """
        Send confirmation that export request was received.

        Args:
            user_email: User's email address
            user_name: User's name
            estimated_completion: Estimated completion time

        Returns:
            True if email sent successfully
        """
        try:
            message = EmailMessage(
                to=user_email,
                subject="Data Export Aangevraagd - SanskritiSetu",
                body=f"""Beste {user_name},

Je verzoek om je persoonsgegevens te exporteren is ontvangen.

We werken aan het verzamelen van je data. Dit kan tot 24 uur duren.
Geschatte voltooiing: {estimated_completion.strftime("%d %B %Y, %H:%M")}

Je ontvangt een email zodra je export klaar is met een veilige download link.

Met vriendelijke groet,
Het SanskritiSetu Privacy Team
""",
                html_body=f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <h2>Data Export Aangevraagd</h2>
    <p>Beste {user_name},</p>
    <p>Je verzoek om je persoonsgegevens te exporteren is ontvangen.</p>
    <div style="background-color: #f0fdf4; padding: 16px; margin: 20px 0; border-left: 4px solid #22c55e;">
        <p><strong>Status:</strong> In behandeling</p>
        <p><strong>Geschatte voltooiing:</strong> {estimated_completion.strftime("%d %B %Y, %H:%M")}</p>
    </div>
    <p>Je ontvangt een email zodra je export klaar is met een veilige download link.</p>
    <p>Met vriendelijke groet,<br>Het SanskritiSetu Privacy Team</p>
</body>
</html>
""",
            )

            success = await self.email_service.send(message)

            if success:
                logger.info(f"Export request confirmation sent to {user_email}")
            else:
                logger.error(f"Failed to send export request confirmation to {user_email}")

            return success

        except Exception as e:
            logger.exception(f"Error sending export request confirmation: {e}")
            return False


# Convenience factory function
def get_dsar_notification_service() -> DSARNotificationService:
    """
    Get a configured DSAR notification service.

    Returns:
        DSARNotificationService configured with the default email service
    """
    from src.core.services.email import get_email_service

    email_service = get_email_service()
    return DSARNotificationService(email_service)
