"""
Service for managing the Design Partner Program.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.partners.models import DesignPartner, PartnerFeedback
from src.core.scheduling.partners.repository import PartnerFeedbackRepository, PartnerRepository

logger = logging.getLogger(__name__)


class PartnerService:
    """
    Service for managing design partners and their feedback.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.partner_repo = PartnerRepository(db, tenant_id)
        self.feedback_repo = PartnerFeedbackRepository(db, tenant_id)

    # ========================================================================
    # Partner Management
    # ========================================================================

    async def register_partner(
        self,
        tenant_id: int,
        name: str,
        industry: str,
        contact_email: str,
        start_date: datetime,
        end_date: datetime,
        contact_name: str | None = None,
        max_users: int = 100,
        allowed_features: list[str] | None = None,
    ) -> DesignPartner:
        """
        Register a new design partner.

        Args:
            tenant_id: The tenant ID for the partner
            name: Company/organization name
            industry: Industry sector
            contact_email: Primary contact email
            start_date: Program start date
            end_date: Program end date
            contact_name: Contact person name
            max_users: Maximum allowed users
            allowed_features: List of feature flags enabled

        Returns:
            Created DesignPartner
        """
        # Check if tenant already has a partner record
        existing = await self.partner_repo.get_by_tenant(tenant_id)
        if existing:
            raise ValueError(f"Tenant {tenant_id} already has a design partner record")

        partner = await self.partner_repo.create(
            tenant_id=tenant_id,
            name=name,
            industry=industry,
            contact_email=contact_email,
            start_date=start_date,
            end_date=end_date,
            contact_name=contact_name,
            max_users=max_users,
            allowed_features=allowed_features or [],
        )

        await self.db.commit()
        logger.info(f"Registered design partner: {name} (tenant: {tenant_id})")

        return partner

    async def activate_partner(self, partner_id: str) -> bool:
        """Activate a partner (move from onboarding to active)."""
        partner = await self.partner_repo.get_by_id(partner_id)
        if not partner:
            return False

        if partner.status != "onboarding":
            raise ValueError(f"Cannot activate partner with status: {partner.status}")

        success = await self.partner_repo.update_status(partner_id, "active")
        if success:
            await self.db.commit()
            logger.info(f"Activated design partner: {partner_id}")

        return success

    async def complete_program(self, partner_id: str) -> bool:
        """Mark partner program as completed."""
        success = await self.partner_repo.update_status(partner_id, "completed")
        if success:
            await self.db.commit()
            logger.info(f"Completed design partner program: {partner_id}")
        return success

    async def suspend_partner(self, partner_id: str, reason: str) -> bool:
        """Suspend a partner from the program."""
        success = await self.partner_repo.update_status(partner_id, "suspended")
        if success:
            await self.db.commit()
            logger.warning(f"Suspended design partner: {partner_id} - {reason}")
        return success

    async def record_usage_metrics(
        self,
        partner_id: str,
        metric_name: str,
        amount: int = 1,
    ) -> bool:
        """Record usage metrics for a partner."""
        success = await self.partner_repo.update_metrics(partner_id, metric_name, amount)
        if success:
            await self.db.commit()
        return success

    # ========================================================================
    # Feedback Management
    # ========================================================================

    async def submit_feedback(
        self,
        partner_id: str,
        feedback_type: str,
        severity: str,
        category: str,
        title: str,
        description: str,
        reported_by: str | None = None,
        reporter_email: str | None = None,
        reproduction_steps: str | None = None,
        expected_behavior: str | None = None,
        actual_behavior: str | None = None,
        environment: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> PartnerFeedback:
        """
        Submit feedback from a partner.

        Returns:
            Created PartnerFeedback with calculated priority
        """
        # Validate partner exists and is active
        partner = await self.partner_repo.get_by_id(partner_id)
        if not partner:
            raise ValueError(f"Partner not found: {partner_id}")

        if not partner.is_active_program():
            logger.warning(f"Feedback submitted for inactive partner: {partner_id}")

        feedback = await self.feedback_repo.create(
            partner_id=partner_id,
            feedback_type=feedback_type,
            severity=severity,
            category=category,
            title=title,
            description=description,
            reported_by=reported_by,
            reporter_email=reporter_email,
            reproduction_steps=reproduction_steps,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            environment=environment,
        )

        await self.db.commit()

        # Log critical/high severity feedback
        if severity in ("critical", "high"):
            logger.warning(f"High priority feedback submitted: {title} (partner: {partner_id})")

        return feedback

    async def assign_feedback(
        self,
        feedback_id: str,
        engineer_id: str,
    ) -> bool:
        """Assign feedback to an engineer."""
        success = await self.feedback_repo.assign(feedback_id, engineer_id)
        if success:
            await self.db.commit()
            logger.info(f"Assigned feedback {feedback_id} to engineer {engineer_id}")
        return success

    async def resolve_feedback(
        self,
        feedback_id: str,
        resolution_notes: str | None = None,
    ) -> bool:
        """Mark feedback as resolved."""
        success = await self.feedback_repo.resolve(feedback_id, resolution_notes)
        if success:
            await self.db.commit()
            logger.info(f"Resolved feedback: {feedback_id}")
        return success

    async def get_priority_feedback(
        self,
        min_severity: str = "high",
        limit: int = 20,
    ) -> list[PartnerFeedback]:
        """Get high priority open feedback items."""
        return await self.feedback_repo.list_open_by_severity(min_severity)

    async def get_feedback_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get comprehensive feedback statistics."""
        return await self.feedback_repo.get_statistics()

    # ========================================================================
    # Dashboard Data
    # ========================================================================

    async def get_partner_dashboard(
        self,
        partner_id: str,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get dashboard data for a specific partner.

        Returns metrics, recent feedback, and program status.
        """
        partner = await self.partner_repo.get_by_id(partner_id)
        if not partner:
            raise ValueError(f"Partner not found: {partner_id}")

        # Get recent feedback
        recent_feedback_list, _ = await self.feedback_repo.list_by_partner(partner_id)

        # Calculate days remaining
        days_remaining = (partner.end_date - datetime.now(timezone.utc)).days

        return {
            "partner": {
                "id": partner.id,
                "name": partner.name,
                "status": partner.status,
                "start_date": partner.start_date,
                "end_date": partner.end_date,
                "days_remaining": max(0, days_remaining),
            },
            "metrics": {
                "total_events_created": partner.total_events_created,
                "total_conflicts_detected": partner.total_conflicts_detected,
                "api_calls_count": partner.api_calls_count,
                "error_count": partner.error_count,
            },
            "recent_feedback": [
                {
                    "id": f.id,
                    "title": f.title,
                    "type": f.feedback_type,
                    "severity": f.severity,
                    "status": f.status,
                    "created_at": f.created_at,
                }
                for f in recent_feedback_list
            ],
        }

    async def get_program_overview(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get overview of entire design partner program.

        Returns summary statistics across all partners.
        """
        # Get all partners
        all_partners_list, _ = await self.partner_repo.list_all()
        active_partners = [p for p in all_partners_list if p.is_active_program()]

        # Get feedback stats
        feedback_stats = await self.feedback_repo.get_statistics()

        # Calculate aggregate metrics
        total_events = sum(p.total_events_created for p in all_partners_list)
        total_conflicts = sum(p.total_conflicts_detected for p in all_partners_list)
        total_api_calls = sum(p.api_calls_count for p in all_partners_list)

        return {
            "program_summary": {
                "total_partners": len(all_partners_list),
                "active_partners": len(active_partners),
                "completed_partners": len(
                    [p for p in all_partners_list if p.status == "completed"]
                ),
            },
            "aggregate_metrics": {
                "total_events_created": total_events,
                "total_conflicts_detected": total_conflicts,
                "total_api_calls": total_api_calls,
            },
            "feedback_summary": feedback_stats,
            "active_partner_list": [
                {
                    "id": p.id,
                    "name": p.name,
                    "industry": p.industry,
                    "days_remaining": max(0, (p.end_date - datetime.now(timezone.utc)).days),
                }
                for p in active_partners
            ],
        }
