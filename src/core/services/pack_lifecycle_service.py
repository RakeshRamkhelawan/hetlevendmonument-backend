"""
Pack Lifecycle Service

Handles pack deactivation logic for packs with "critical" health status.
Part of Paperclip Pipeline Integration - Plan 4, Task 3.

This service:
- Identifies packs eligible for deactivation (critical health + grace period expired)
- Performs soft deletion (status = 'archived')
- Sends notifications to department owners
- Processes warning notifications for at-risk packs

Usage:
    from src.core.services.pack_lifecycle_service import pack_lifecycle_service
    await pack_lifecycle_service.process_deactivations()
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select

from src.core.config.pack_lifecycle_config import pack_lifecycle_config
from src.core.database.session import get_db_session
from src.core.procedures.models import DomainPack
from src.core.services.email_templates import email_templates
from src.core.services.notification_service import notification_service

logger = logging.getLogger(__name__)


class PackLifecycleService:
    """
    Service for managing pack lifecycle operations.

    Handles deactivation of packs that have been in "critical" health status
    beyond the grace period, and sends appropriate notifications.
    """

    DEACTIVATION_WARNING_DAYS: int = 60
    DEACTIVATION_CRITICAL_DAYS: int = 90
    ERROR_THRESHOLD_WARNING: float = 0.05
    ERROR_THRESHOLD_CRITICAL: float = 0.10
    GRACE_PERIOD_DAYS: int = 30

    async def get_packs_for_deactivation(self) -> list[DomainPack]:
        """
        Get packs with health_status = 'critical'.

        These packs are candidates for deactivation if the grace period
        has expired.

        Returns:
            List of DomainPack objects with critical health status
        """
        async with get_db_session() as db:
            result = await db.execute(
                select(DomainPack).where(DomainPack.health_status == "critical")
            )
            return list(result.scalars().all())

    async def get_packs_for_warning(self) -> list[DomainPack]:
        """
        Get packs with health_status = 'warning'.

        These packs are at risk and should trigger warning notifications
        to department owners.

        Returns:
            List of DomainPack objects with warning health status
        """
        async with get_db_session() as db:
            result = await db.execute(
                select(DomainPack).where(DomainPack.health_status == "warning")
            )
            return list(result.scalars().all())

    def check_grace_period(self, pack: DomainPack) -> bool:
        """
        Check if grace period has expired since last health check.

        Args:
            pack: DomainPack to check

        Returns:
            True if grace period has expired, False otherwise
        """
        if pack.last_health_check is None:
            return True
        grace_period_ago = datetime.now(timezone.utc) - timedelta(days=self.GRACE_PERIOD_DAYS)
        return pack.last_health_check < grace_period_ago

    async def deactivate_pack(self, pack_id: UUID, reason: str, db_session: Any = None) -> bool:
        """
        Soft delete pack by setting status to 'archived'.

        Args:
            pack_id: UUID of the pack to deactivate
            reason: Human-readable reason for deactivation
            db_session: Optional database session to use (for testing)

        Returns:
            True if pack was found and deactivated, False otherwise
        """
        if db_session:
            # Use provided session for testing
            pack = await db_session.get(DomainPack, pack_id)
            if pack:
                pack.status = "archived"
                pack.updated_at = datetime.now(timezone.utc)
                await db_session.commit()
                logger.info(f"Pack {pack_id} deactivated: {reason}")
                return True
            return False
        else:
            async with get_db_session() as db:
                pack = await db.get(DomainPack, pack_id)
                if pack:
                    pack.status = "archived"
                    pack.updated_at = datetime.now(timezone.utc)
                    await db.commit()
                    logger.info(f"Pack {pack_id} deactivated: {reason}")
                    return True
                return False

    async def notify_department_owner(
        self, department_id: UUID | None, pack_id: UUID, status: str
    ) -> None:
        """
        Send notification to department owner about pack status change.

        Args:
            department_id: UUID of the department (optional)
            pack_id: UUID of the pack
            status: Current status ('warning', 'critical', or 'deactivated')
        """
        # Get pack details for the notification
        async with get_db_session() as db:
            pack = await db.get(DomainPack, pack_id)
            pack_name = pack.name if pack else str(pack_id)

        # Log notification (placeholder for actual notification logic)
        # Could be email, in-app, WebSocket, or Slack
        logger.info(
            f"Notification: Pack '{pack_name}' (ID: {pack_id}) in department "
            f"{department_id} is {status}"
        )

        # Send WebSocket notification if notification service available
        try:
            if status == "deactivated":
                await notification_service.broadcast_system(
                    title="Pack Deactivated",
                    message=f"Pack '{pack_name}' has been deactivated due to inactivity",
                )
            elif status == "warning":
                # Could send to specific department users
                pass
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")

    async def send_deactivation_email(
        self, pack: DomainPack, email: str, is_warning: bool = False
    ) -> bool:
        """
        Send deactivation-related email to department owner.

        Args:
            pack: DomainPack that is being warned or deactivated
            email: Recipient email address
            is_warning: True for warning email, False for deactivation notice

        Returns:
            True if email was rendered successfully
        """
        try:
            from src.core.services.email import EmailMessage, get_email_service

            if is_warning:
                # Send warning email
                template_name = "pack_deactivation_warning.html"
                subject = f"Warning: Pack '{pack.name}' at Risk of Deactivation"
                context = {
                    "pack_name": pack.name,
                    "pack_id": str(pack.id),
                    "department": pack.department,
                    "grace_period_days": self.GRACE_PERIOD_DAYS,
                    "critical_days": self.DEACTIVATION_CRITICAL_DAYS,
                }
            else:
                # Send deactivation notice
                template_name = "pack_deactivated.html"
                subject = f"Pack '{pack.name}' Has Been Deactivated"
                context = {
                    "pack_name": pack.name,
                    "pack_id": str(pack.id),
                    "department": pack.department,
                    "deactivation_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                }

            rendered = email_templates.render(template_name, subject, context)

            email_service = get_email_service()
            msg = EmailMessage(
                to=email,
                subject=rendered.subject,
                body=rendered.text_body or rendered.subject,
                html_body=rendered.html_body,
            )
            # Het resultaat telt: zonder mailinstelling geeft de dienst `False` (en een ERROR), en dan mag
            # hieronder niet "sent" staan.
            if not await email_service.send(msg):
                return False

            logger.info(f"Deactivation email sent to {email} for pack {pack.id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send deactivation email: {e}")
            return False

    async def process_deactivations(self, db_session: Any = None) -> dict[str, Any]:
        """
        Main method: process all pack deactivations and warnings.

        This method:
        1. Gets all packs with 'critical' health status
        2. Deactivates those that have exceeded the grace period
        3. Sends notifications for deactivated packs
        4. Gets all packs with 'warning' health status
        5. Sends warning notifications for at-risk packs

        Args:
            db_session: Optional database session to use (for testing).
                       If None, creates a new session.

        Returns:
            Dictionary with counts of processed packs
        """
        result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "deactivated_count": 0,
            "warning_count": 0,
            "notification_count": 0,
            "errors": [],
        }

        # Check if auto-deactivation is enabled
        if not pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED:
            logger.info("Auto-deactivation is disabled. Only notifications will be sent.")

        try:
            # Get critical packs
            if db_session:
                # Use provided session for testing
                from sqlalchemy import select

                result_query = await db_session.execute(
                    select(DomainPack).where(DomainPack.health_status == "critical")
                )
                critical_packs = list(result_query.scalars().all())
            else:
                critical_packs = await self.get_packs_for_deactivation()
            logger.info(f"Found {len(critical_packs)} packs with critical health")

            for pack in critical_packs:
                try:
                    if self.check_grace_period(pack):
                        # Check if auto-deactivation is enabled
                        if pack_lifecycle_config.PACK_DEACTIVATION_AUTO_ENABLED:
                            success = await self.deactivate_pack(
                                pack.id,
                                f"No usage for {self.DEACTIVATION_CRITICAL_DAYS} days",
                            )
                            if success:
                                result["deactivated_count"] += 1
                                await self.notify_department_owner(
                                    None,  # department_id not directly on pack
                                    pack.id,
                                    "deactivated",
                                )
                                result["notification_count"] += 1
                        else:
                            # Just notify that pack would be deactivated
                            logger.warning(
                                f"Pack {pack.id} ({pack.name}) would be deactivated "
                                f"(auto-deactivation disabled)"
                            )
                            await self.notify_department_owner(
                                None, pack.id, "critical - pending deactivation"
                            )
                            result["notification_count"] += 1
                    else:
                        # Still in grace period, notify
                        await self.notify_department_owner(
                            None, pack.id, "critical - grace period active"
                        )
                        result["notification_count"] += 1

                except Exception as e:
                    error_msg = f"Error processing critical pack {pack.id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

            # Get warning packs and notify
            if db_session:
                # Use provided session for testing
                from sqlalchemy import select

                result_query = await db_session.execute(
                    select(DomainPack).where(DomainPack.health_status == "warning")
                )
                warning_packs = list(result_query.scalars().all())
            else:
                warning_packs = await self.get_packs_for_warning()
            logger.info(f"Found {len(warning_packs)} packs with warning health")

            for pack in warning_packs:
                try:
                    await self.notify_department_owner(None, pack.id, "warning")
                    result["warning_count"] += 1
                    result["notification_count"] += 1
                except Exception as e:
                    error_msg = f"Error processing warning pack {pack.id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)

            logger.info(
                f"Pack lifecycle processing complete: "
                f"{result['deactivated_count']} deactivated, "
                f"{result['warning_count']} warnings, "
                f"{result['notification_count']} notifications"
            )

        except Exception as e:
            error_msg = f"Error in process_deactivations: {e}"
            logger.error(error_msg, exc_info=True)
            result["errors"].append(error_msg)

        return result


# Singleton instance
pack_lifecycle_service = PackLifecycleService()
