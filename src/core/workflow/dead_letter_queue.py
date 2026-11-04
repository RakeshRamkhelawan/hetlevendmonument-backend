"""
Dead Letter Queue (DLQ) - Poison Pill Handling & Failed Task Recovery

Provides:
- DeadLetterEntry model for persisting failed tasks
- DeadLetterQueue service for enqueue/retry/resolve operations
- Poison pill detection (tasks that fail repeatedly)
- Tenant isolation for DLQ entries
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DLQStatus(str, enum.Enum):
    """Status for Dead Letter Queue entries."""

    PENDING = "pending"  # Failed, waiting for retry or resolution
    RETRYING = "retrying"  # Currently being retried
    RESOLVED = "resolved"  # Manually resolved
    EXPIRED = "expired"  # Auto-expired after max retention


class DeadLetterEntry(Base):  # type: ignore[misc]
    """
        Database model for failed tasks in Dead Letter Queue.

        Stores complete context for failed tasks to enable:
        - Root cause analysis
    - Manual retry
        - Audit trail
    """

    __tablename__ = "dead_letter_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Original task context
    original_task_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    execution_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Error context
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # Exception class name

    # Retry context
    retry_count: Mapped[int | None] = mapped_column(Integer, default=0)
    max_retries: Mapped[int | None] = mapped_column(Integer, default=3)

    # Status
    status: Mapped[str] = mapped_column(String(20), default=DLQStatus.PENDING.value, nullable=False)

    # Timestamps
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Resolution context
    resolved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional metadata (JSON)
    task_metadata: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON string with task context

    # Indexes
    __table_args__ = (
        Index("idx_dlq_tenant_status", "tenant_id", "status"),
        Index("idx_dlq_execution", "execution_id"),
        Index("idx_dlq_failed_at", "failed_at"))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert entry to dictionary."""
        return {
            "id": self.id,
            "original_task_id": self.original_task_id,
            "execution_id": self.execution_id,
            "tenant_id": self.tenant_id,
            "workflow_id": self.workflow_id,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "status": self.status,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "last_retry_at": self.last_retry_at.isoformat() if self.last_retry_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "resolution_notes": self.resolution_notes,
        }

    @property
    def is_poison_pill(self) -> bool:
        """Check if this entry is a potential poison pill (>3 failures)."""
        return (self.retry_count or 0) >= 3


class DeadLetterQueue:
    """
    Service for managing Dead Letter Queue operations.

    Provides:
    - Enqueue failed tasks
    - List entries with filtering
    - Retry entries
    - Resolve entries
    - Poison pill detection
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(
        self,
        original_task_id: str,
        execution_id: str,
        tenant_id: int,
        error_message: str,
        stack_trace: str | None = None,
        error_type: str | None = None,
        workflow_id: str | None = None,
        retry_count: int = 0,
        max_retries: int = 3,
        task_metadata: dict[str, Any] | None = None) -> DeadLetterEntry:  # TODO(TYPE): replace Any with concrete type
        """
        Add a failed task to the Dead Letter Queue.

        Args:
            original_task_id: ID of the failed task
            execution_id: Workflow execution ID
            tenant_id: Tenant ID for isolation
            error_message: Error message
            stack_trace: Full stack trace
            error_type: Exception class name
            workflow_id: Workflow definition ID
            retry_count: Number of retries already attempted
            max_retries: Maximum retry attempts
            task_metadata: Additional task context (JSON-serializable)

        Returns:
            Created DeadLetterEntry
        """
        import json

        entry = DeadLetterEntry(
            original_task_id=original_task_id,
            execution_id=execution_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            error_message=error_message,
            stack_trace=stack_trace,
            error_type=error_type,
            retry_count=retry_count,
            max_retries=max_retries,
            status=DLQStatus.PENDING.value,
            task_metadata=json.dumps(task_metadata) if task_metadata else None)

        self._session.add(entry)
        await self._session.commit()

        logger.warning(
            f"Task {original_task_id} added to DLQ (execution={execution_id}, "
            f"tenant={tenant_id}, retry_count={retry_count})"
        )

        # Emit event
        await self._emit_event("workflow.task.dead_lettered", entry)

        return entry

    async def list_entries(
        self,
        tenant_id: int,
        status: DLQStatus | None = None,
        limit: int = 100,
        offset: int = 0) -> list[DeadLetterEntry]:
        """
        List DLQ entries for a tenant.

        Args:
            tenant_id: Tenant ID
            status: Filter by status (optional)
            limit: Maximum entries to return
            offset: Pagination offset

        Returns: List[Any] of DeadLetterEntry objects  # TODO(TYPE): replace Any with concrete type
        """
        from sqlalchemy import select

        query = select(DeadLetterEntry).where(DeadLetterEntry.tenant_id == tenant_id)

        if status:
            query = query.where(DeadLetterEntry.status == status.value)

        query = query.order_by(DeadLetterEntry.failed_at.desc())
        query = query.offset(offset).limit(limit)

        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_entry(
        self,
        entry_id: int,
        tenant_id: int) -> DeadLetterEntry | None:
        """
        Get a specific DLQ entry.

        Args:
            entry_id: Entry ID
            tenant_id: Tenant ID (for isolation check)

        Returns:
            DeadLetterEntry or None if not found
        """
        from sqlalchemy import select

        result = await self._session.execute(
            select(DeadLetterEntry).where(
                DeadLetterEntry.id == entry_id,
                DeadLetterEntry.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def retry_entry(
        self,
        entry_id: int,
        tenant_id: int) -> bool:
        """
        Retry a DLQ entry.

        Args:
            entry_id: Entry ID to retry
            tenant_id: Tenant ID

        Returns:
            True if retry initiated, False if not found or already resolved
        """
        entry = await self.get_entry(entry_id, tenant_id)

        if not entry:
            logger.warning(f"DLQ entry {entry_id} not found for tenant {tenant_id}")
            return False

        if entry.status == DLQStatus.RESOLVED.value:
            logger.warning(f"DLQ entry {entry_id} already resolved")
            return False

        # Update entry status
        entry.status = DLQStatus.RETRYING.value
        entry.last_retry_at = datetime.now(timezone.utc)
        entry.retry_count = (entry.retry_count or 0) + 1

        await self._session.commit()

        logger.info(f"DLQ entry {entry_id} marked for retry (attempt {entry.retry_count})")

        # Emit retry event
        await self._emit_event("workflow.task.retry_from_dlq", entry)

        return True

    async def resolve_entry(
        self,
        entry_id: int,
        tenant_id: int,
        resolved_by: int,
        notes: str | None = None) -> bool:
        """
        Manually resolve a DLQ entry.

        Args:
            entry_id: Entry ID to resolve
            tenant_id: Tenant ID
            resolved_by: User ID who resolved the entry
            notes: Resolution notes

        Returns:
            True if resolved, False if not found
        """
        entry = await self.get_entry(entry_id, tenant_id)

        if not entry:
            return False

        entry.status = DLQStatus.RESOLVED.value
        entry.resolved_at = datetime.now(timezone.utc)
        entry.resolved_by = resolved_by
        entry.resolution_notes = notes

        await self._session.commit()

        logger.info(f"DLQ entry {entry_id} resolved by user {resolved_by}")

        return True

    async def get_poison_pills(
        self,
        tenant_id: int,
        threshold: int = 3,
        limit: int = 100) -> list[DeadLetterEntry]:
        """
        Get potential poison pills (tasks that failed >N times).

        Args:
            tenant_id: Tenant ID
            threshold: Minimum retry count to be considered poison
            limit: Maximum entries to return

        Returns: List[Any] of potential poison pill entries  # TODO(TYPE): replace Any with concrete type
        """
        from sqlalchemy import select

        result = await self._session.execute(
            select(DeadLetterEntry)
            .where(DeadLetterEntry.tenant_id == tenant_id)
            .where(DeadLetterEntry.retry_count >= threshold)
            .where(DeadLetterEntry.status != DLQStatus.RESOLVED.value)
            .order_by(DeadLetterEntry.retry_count.desc())
            .limit(limit)
        )

        return list(result.scalars().all())

    async def count_by_status(
        self,
        tenant_id: int) -> dict[str, int]:
        """
        Count DLQ entries by status.

        Args:
            tenant_id: Tenant ID

        Returns: Dict[str, Any]ionary mapping status to count  # TODO(TYPE): replace Any with concrete type
        """
        from sqlalchemy import func, select

        result = await self._session.execute(
            select(DeadLetterEntry.status, func.count(DeadLetterEntry.id))
            .where(DeadLetterEntry.tenant_id == tenant_id)
            .group_by(DeadLetterEntry.status)
        )

        return {status: count for status, count in result.all()}

    async def _emit_event(self, event_type: str, entry: DeadLetterEntry) -> None:
        """Emit an event for DLQ operations."""
        # This would integrate with the event system
        # For now, just log
        logger.debug(f"Event emitted: {event_type} for entry {entry.id}")


class PoisonPillDetector:
    """
    Detects and handles poison pills in workflows.

    A poison pill is a task that consistently fails even after retries,
    potentially blocking workflow execution.
    """

    def __init__(self, dlq: DeadLetterQueue, threshold: int = 3) -> None:
        self.dlq = dlq
        self.threshold = threshold

    async def check_workflow(
        self,
        execution_id: str,
        tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Check a workflow for poison pills.

        Args:
            execution_id: Workflow execution ID
            tenant_id: Tenant ID

        Returns: Dict[str, Any]ionary with poison pill analysis  # TODO(TYPE): replace Any with concrete type
        """
        from sqlalchemy import select

        # Get all DLQ entries for this execution
        result = await self.dlq._session.execute(
            select(DeadLetterEntry)
            .where(DeadLetterEntry.execution_id == execution_id)
            .where(DeadLetterEntry.tenant_id == tenant_id)
        )
        entries = result.scalars().all()

        if not entries:
            return {"has_poison_pills": False, "poison_pill_count": 0, "total_entries": 0}

        # Count poison pills
        poison_pills = [e for e in entries if (e.retry_count or 0) >= self.threshold]
        total = len(entries)
        poison_count = len(poison_pills)

        # Check if >50% are poison pills
        is_blocked = poison_count > (total / 2)

        return {
            "has_poison_pills": poison_count > 0,
            "poison_pill_count": poison_count,
            "total_entries": total,
            "is_blocked": is_blocked,
            "threshold": self.threshold,
            "poison_pill_ids": [e.id for e in poison_pills],
        }

    async def should_block_workflow(
        self,
        execution_id: str,
        tenant_id: int) -> bool:
        """
        Determine if a workflow should be blocked due to poison pills.

        Args:
            execution_id: Workflow execution ID
            tenant_id: Tenant ID

        Returns:
            True if workflow should be blocked (>50% poison pills)
        """
        analysis = await self.check_workflow(execution_id, tenant_id)
        return bool(analysis.get("is_blocked", False))
