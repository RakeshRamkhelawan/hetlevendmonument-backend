"""
Repository layer for AIQualityEvent model
Handles recording and retrieval of AI quality events for observability
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AIQualityEvent
from .schemas import AIQualityEventCreate


class AIQualityEventRepository:
    """Repository for AI quality event database operations with tenant isolation"""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self._tenant_id = tenant_id

    async def record_event(self, data: AIQualityEventCreate) -> AIQualityEvent:
        """
        Record a new AI quality event with tenant isolation

        Args:
            data: AIQualityEventCreate schema with event details

        Returns:
            Created AIQualityEvent model
        """
        event = AIQualityEvent(
            tenant_id=self._tenant_id,
            execution_id=data.execution_id,
            event_type=data.event_type,
            severity=data.severity,
            details=data.details,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def get_by_id(self, event_id: UUID) -> AIQualityEvent | None:
        """
        Get quality event by ID, ensuring it belongs to the tenant

        Args:
            event_id: Quality event ID

        Returns:
            AIQualityEvent if found and belongs to tenant, None otherwise
        """
        stmt = select(AIQualityEvent).where(
            and_(
                AIQualityEvent.id == event_id,
                AIQualityEvent.tenant_id == self._tenant_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_execution(self, execution_id: UUID) -> list[AIQualityEvent]:
        """
        List all quality events for a procedure execution (tenant isolated)

        Args:
            execution_id: Procedure execution ID

        Returns: List[Any] of AIQualityEvent objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(AIQualityEvent)
            .where(
                and_(
                    AIQualityEvent.execution_id == execution_id,
                    AIQualityEvent.tenant_id == self._tenant_id,
                )
            )
            .order_by(AIQualityEvent.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_type(self, event_type: str) -> list[AIQualityEvent]:
        """
        List all events of a specific type (tenant isolated)

        Args:
            event_type: Event type (hallucination, low_confidence, policy_violation, timeout)

        Returns: List[Any] of AIQualityEvent objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(AIQualityEvent)
            .where(
                and_(
                    AIQualityEvent.event_type == event_type,
                    AIQualityEvent.tenant_id == self._tenant_id,
                )
            )
            .order_by(AIQualityEvent.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_severity(self, severity: str) -> list[AIQualityEvent]:
        """
        List all events with specific severity (tenant isolated)

        Args:
            severity: Severity level (info, warning, error, critical)

        Returns: List[Any] of AIQualityEvent objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(AIQualityEvent)
            .where(
                and_(
                    AIQualityEvent.severity == severity,
                    AIQualityEvent.tenant_id == self._tenant_id,
                )
            )
            .order_by(AIQualityEvent.created_at.desc())
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_critical_events(self, limit: int = 100) -> list[AIQualityEvent]:
        """
        List recent critical events for monitoring/alerting (tenant isolated)

        Args:
            limit: Max events to return

        Returns: List[Any] of critical AIQualityEvent objects  # TODO(TYPE): replace Any with concrete type
        """
        stmt = (
            select(AIQualityEvent)
            .where(
                and_(
                    AIQualityEvent.severity == "critical",
                    AIQualityEvent.tenant_id == self._tenant_id,
                )
            )
            .order_by(AIQualityEvent.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_event_stats(self, execution_id: UUID) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get statistics of quality events for an execution (tenant isolated)

        Args:
            execution_id: Procedure execution ID

        Returns: Dict[str, Any]ionary with event counts by type and severity  # TODO(TYPE): replace Any with concrete type
        """
        # Count by event type
        type_stmt = (
            select(AIQualityEvent.event_type, func.count(AIQualityEvent.id).label("count"))
            .where(
                and_(
                    AIQualityEvent.execution_id == execution_id,
                    AIQualityEvent.tenant_id == self._tenant_id,
                )
            )
            .group_by(AIQualityEvent.event_type)
        )

        type_result = await self.db.execute(type_stmt)
        type_counts = {row[0]: row[1] for row in type_result.fetchall()}

        # Count by severity
        severity_stmt = (
            select(AIQualityEvent.severity, func.count(AIQualityEvent.id).label("count"))
            .where(
                and_(
                    AIQualityEvent.execution_id == execution_id,
                    AIQualityEvent.tenant_id == self._tenant_id,
                )
            )
            .group_by(AIQualityEvent.severity)
        )

        severity_result = await self.db.execute(severity_stmt)
        severity_counts = {row[0]: row[1] for row in severity_result.fetchall()}

        return {
            "execution_id": str(execution_id),
            "by_type": type_counts,
            "by_severity": severity_counts,
            "total": sum(type_counts.values()),
        }

    async def commit(self) -> None:
        """Commit database transaction"""
        await self.db.commit()

    async def rollback(self) -> None:
        """Rollback database transaction"""
        await self.db.rollback()
