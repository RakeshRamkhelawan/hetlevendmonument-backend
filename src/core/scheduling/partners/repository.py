"""
Repository for DesignPartner and PartnerFeedback models.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.partners.models import DesignPartner, PartnerFeedback


class PartnerRepository:
    """Repository for design partner operations with tenant isolation."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self._tenant_id = tenant_id

    # ========================================================================
    # Design Partner CRUD
    # ========================================================================

    async def get_by_id(self, partner_id: str) -> DesignPartner | None:
        """Get partner by ID, ensuring it belongs to the tenant."""
        result = await self.db.execute(
            select(DesignPartner).where(
                and_(
                    DesignPartner.id == partner_id,
                    DesignPartner.tenant_id == self._tenant_id,
                    DesignPartner.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(self, tenant_id: int) -> DesignPartner | None:
        """Get partner by tenant ID."""
        result = await self.db.execute(
            select(DesignPartner).where(
                and_(
                    DesignPartner.tenant_id == tenant_id,
                    DesignPartner.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        status: str | None = None,
        industry: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[DesignPartner], int]:
        """List all partners with optional filters and pagination.

        Returns:
            Tuple of (partners list, total count)
        """
        query = select(DesignPartner).where(DesignPartner.deleted_at.is_(None))

        if status:
            query = query.where(DesignPartner.status == status)
        if industry:
            query = query.where(DesignPartner.industry == industry)

        # Get total count
        from sqlalchemy import func

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Apply pagination
        query = query.order_by(DesignPartner.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def list_active(self) -> list[DesignPartner]:
        """List all active partners (currently in program)."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(DesignPartner).where(
                and_(
                    DesignPartner.status == "active",
                    DesignPartner.start_date <= now,
                    DesignPartner.end_date >= now,
                    DesignPartner.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def create(
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
        """Create a new design partner."""
        partner = DesignPartner(
            tenant_id=tenant_id,
            name=name,
            industry=industry,
            contact_email=contact_email,
            contact_name=contact_name,
            status="onboarding",
            start_date=start_date,
            end_date=end_date,
            max_users=max_users,
            allowed_features=allowed_features or [],
        )
        self.db.add(partner)
        await self.db.flush()
        return partner

    async def update_status(
        self,
        partner_id: str,
        status: str,
    ) -> bool:
        """Update partner status."""
        partner = await self.get_by_id(partner_id)
        if not partner:
            return False

        partner.status = status
        await self.db.flush()
        return True

    async def update_metrics(
        self,
        partner_id: str,
        metric_name: str,
        amount: int = 1,
    ) -> bool:
        """Update partner metrics."""
        partner = await self.get_by_id(partner_id)
        if not partner:
            return False

        partner.increment_metric(metric_name, amount)
        await self.db.flush()
        return True

    async def soft_delete(self, partner_id: str) -> bool:
        """Soft delete a partner."""
        partner = await self.get_by_id(partner_id)
        if not partner:
            return False

        partner.deleted_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True


class PartnerFeedbackRepository:
    """Repository for partner feedback operations with tenant isolation via join."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self._tenant_id = tenant_id

    # ========================================================================
    # Feedback CRUD
    # ========================================================================

    async def get_by_id(self, feedback_id: str) -> PartnerFeedback | None:
        """Get feedback by ID, ensuring it belongs to the tenant via partner."""
        # Join with DesignPartner to enforce tenant isolation
        stmt = (
            select(PartnerFeedback)
            .join(DesignPartner, PartnerFeedback.partner_id == DesignPartner.id)
            .where(
                and_(
                    PartnerFeedback.id == feedback_id,
                    DesignPartner.tenant_id == self._tenant_id,
                )
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_partner(
        self,
        partner_id: str,
        status: str | None = None,
        severity: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PartnerFeedback], int]:
        """List feedback for a partner with pagination (tenant isolated).

        Returns:
            Tuple of (feedback list, total count)
        """
        # Join with DesignPartner to enforce tenant isolation
        query = (
            select(PartnerFeedback)
            .join(DesignPartner, PartnerFeedback.partner_id == DesignPartner.id)
            .where(
                and_(
                    PartnerFeedback.partner_id == partner_id,
                    DesignPartner.tenant_id == self._tenant_id,
                )
            )
        )

        if status:
            query = query.where(PartnerFeedback.status == status)
        if severity:
            query = query.where(PartnerFeedback.severity == severity)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Apply pagination
        query = query.order_by(PartnerFeedback.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def list_all(
        self,
        status: str | None = None,
        severity: str | None = None,
        category: str | None = None,
        assigned_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[PartnerFeedback], int]:
        """List all feedback with optional filters and pagination (tenant isolated).

        Returns:
            Tuple of (feedback list, total count)
        """
        # Join with DesignPartner to enforce tenant isolation
        query = (
            select(PartnerFeedback)
            .join(DesignPartner, PartnerFeedback.partner_id == DesignPartner.id)
            .where(DesignPartner.tenant_id == self._tenant_id)
        )

        if status:
            query = query.where(PartnerFeedback.status == status)
        if severity:
            query = query.where(PartnerFeedback.severity == severity)
        if category:
            query = query.where(PartnerFeedback.category == category)
        if assigned_to:
            query = query.where(PartnerFeedback.assigned_to == assigned_to)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.db.scalar(count_query) or 0

        # Apply pagination
        query = query.order_by(PartnerFeedback.priority.desc(), PartnerFeedback.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def list_open_by_severity(
        self,
        min_severity: str = "high",
    ) -> list[PartnerFeedback]:
        """List open feedback items by minimum severity."""
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        min_level = severity_order.get(min_severity, 3)

        # Get all open items and filter by severity level
        result = await self.db.execute(
            select(PartnerFeedback).where(PartnerFeedback.status.in_(["open", "in_progress"]))
        )
        all_open = result.scalars().all()

        # Filter by severity level
        filtered = [f for f in all_open if severity_order.get(f.severity, 0) >= min_level]

        # Sort by priority
        filtered.sort(key=lambda f: f.priority, reverse=True)

        return filtered

    async def create(
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
        """Create new feedback with tenant isolation verification."""
        # Verify partner belongs to this tenant
        partner = await self.db.execute(
            select(DesignPartner).where(
                and_(
                    DesignPartner.id == partner_id,
                    DesignPartner.tenant_id == self._tenant_id,
                )
            )
        )
        if not partner.scalar_one_or_none():
            raise ValueError(
                f"Partner {partner_id} not found or does not belong to tenant {self._tenant_id}"
            )

        feedback = PartnerFeedback(
            partner_id=partner_id,
            reported_by=reported_by,
            reporter_email=reporter_email,
            feedback_type=feedback_type,
            severity=severity,
            category=category,
            title=title,
            description=description,
            reproduction_steps=reproduction_steps,
            expected_behavior=expected_behavior,
            actual_behavior=actual_behavior,
            environment=environment,
        )

        # Calculate initial priority
        feedback.priority = feedback.calculate_priority()

        self.db.add(feedback)
        await self.db.flush()
        return feedback

    async def assign(
        self,
        feedback_id: str,
        engineer_id: str,
    ) -> bool:
        """Assign feedback to an engineer."""
        feedback = await self.get_by_id(feedback_id)
        if not feedback:
            return False

        feedback.assign(engineer_id)
        await self.db.flush()
        return True

    async def resolve(
        self,
        feedback_id: str,
        notes: str | None = None,
    ) -> bool:
        """Mark feedback as resolved."""
        feedback = await self.get_by_id(feedback_id)
        if not feedback:
            return False

        feedback.resolve(notes)
        await self.db.flush()
        return True

    async def update_priority(self, feedback_id: str, priority: int) -> bool:
        """Update feedback priority."""
        feedback = await self.get_by_id(feedback_id)
        if not feedback:
            return False

        feedback.priority = priority
        await self.db.flush()
        return True

    # ========================================================================
    # Statistics
    # ========================================================================

    async def get_statistics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get feedback statistics."""
        from sqlalchemy import func

        # Count by status
        status_counts = await self.db.execute(
            select(PartnerFeedback.status, func.count(PartnerFeedback.id)).group_by(
                PartnerFeedback.status
            )
        )
        by_status = {row[0]: row[1] for row in status_counts.all()}

        # Count by severity
        severity_counts = await self.db.execute(
            select(PartnerFeedback.severity, func.count(PartnerFeedback.id)).group_by(
                PartnerFeedback.severity
            )
        )
        by_severity = {row[0]: row[1] for row in severity_counts.all()}

        # Count by category
        category_counts = await self.db.execute(
            select(PartnerFeedback.category, func.count(PartnerFeedback.id)).group_by(
                PartnerFeedback.category
            )
        )
        by_category = {row[0]: row[1] for row in category_counts.all()}

        return {
            "by_status": by_status,
            "by_severity": by_severity,
            "by_category": by_category,
            "total": sum(by_status.values()),
        }
