"""
Conflict resolution service for calendar synchronization.

Detects and resolves conflicts between local and external calendar events.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.conflicts.strategies import (
    AutoResolveStrategy,
    ConflictResolutionStrategy,
    CreateDuplicateStrategy,
    KeepExternalStrategy,
    KeepLocalStrategy,
    MergeStrategy,
    ResolutionResult,
)
from src.core.scheduling.integrations.base_provider import ExternalEvent
from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.repository import CalendarEventRepository
from src.core.scheduling.webhooks.models import SyncConflict
from src.core.scheduling.webhooks.repository import SyncConflictRepository

logger = logging.getLogger(__name__)


class ConflictResolutionService:
    """
    Service for detecting and resolving calendar sync conflicts.

    A conflict occurs when:
    1. Both local and external versions of an event have been modified
    2. External event is deleted while local exists
    3. Local event is modified while external was also changed
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.conflict_repo = SyncConflictRepository(db, tenant_id)
        self.event_repo = CalendarEventRepository(db)

        # Initialize strategies
        self.strategies: dict[str, ConflictResolutionStrategy] = {
            "keep_local": KeepLocalStrategy(),
            "keep_external": KeepExternalStrategy(),
            "merge": MergeStrategy(),
            "create_duplicate": CreateDuplicateStrategy(),
            "auto": AutoResolveStrategy(),
        }

    # ========================================================================
    # Conflict Detection
    # ========================================================================

    async def detect_conflicts(
        self,
        tenant_id: int,
        integration_id: str,
        external_events: list[ExternalEvent],
    ) -> list[SyncConflict]:
        """
        Detect conflicts between local events and external events.

        Args:
            tenant_id: The tenant ID for isolation
            integration_id: The calendar integration ID
            external_events: List of external events to check

        Returns:
            List of detected conflicts
        """
        conflicts = []

        for ext_event in external_events:
            # Check if we have a local event for this external event
            local_event = await self._find_local_event(tenant_id, ext_event.external_id)

            if not local_event:
                # No local event - this is a new external event, not a conflict
                continue

            # Check for conflicts
            conflict_type = self._determine_conflict_type(local_event, ext_event)

            if conflict_type:
                conflict = await self._create_conflict_record(
                    integration_id=integration_id,
                    local_event=local_event,
                    external_event=ext_event,
                    conflict_type=conflict_type,
                )
                conflicts.append(conflict)

        logger.info(f"Detected {len(conflicts)} conflicts for integration {integration_id}")
        return conflicts

    def _determine_conflict_type(
        self,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
    ) -> str | None:
        """
        Determine the type of conflict between local and external events.

        Returns:
            Conflict type string or None if no conflict
        """
        # Check if external was deleted
        if external_event.status in ("cancelled", "deleted"):
            return "deleted_externally"

        # Check for time conflicts
        time_changed = (
            external_event.start_time != local_event.start_time
            or external_event.end_time != local_event.end_time
        )

        # Check for content conflicts
        content_changed = (
            external_event.title != local_event.title
            or external_event.description != local_event.description
            or external_event.location != local_event.location
        )

        if time_changed and content_changed:
            return "updated_both"
        elif time_changed:
            return "time_overlap"
        elif content_changed:
            return "title_mismatch"

        # No conflict
        return None

    async def _find_local_event(
        self,
        tenant_id: int,
        external_event_id: str,
    ) -> CalendarEvent | None:
        """Find local event by external event ID with tenant isolation."""
        from sqlalchemy import and_, select

        result = await self.db.execute(
            select(CalendarEvent).where(
                and_(
                    CalendarEvent.tenant_id == tenant_id,
                    CalendarEvent.metadata_json["external_id"].as_string() == external_event_id,
                    CalendarEvent.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def _create_conflict_record(
        self,
        integration_id: str,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
        conflict_type: str,
    ) -> SyncConflict:
        """Create a conflict record in the database."""
        # Determine severity
        severity = self._determine_severity(conflict_type, local_event, external_event)

        # Create snapshots
        local_snapshot = {
            "title": local_event.title,
            "description": local_event.description,
            "start_time": local_event.start_time.isoformat(),
            "end_time": local_event.end_time.isoformat(),
            "location": local_event.location,
            "status": local_event.status,
            "updated_at": (local_event.updated_at.isoformat() if local_event.updated_at else None),
        }

        external_snapshot = {
            "title": external_event.title,
            "description": external_event.description,
            "start_time": external_event.start_time.isoformat(),
            "end_time": external_event.end_time.isoformat(),
            "location": external_event.location,
            "status": external_event.status,
        }

        # Check if conflict already exists
        existing = await self._find_existing_conflict(
            integration_id, str(local_event.id), external_event.external_id
        )

        if existing and existing.resolution_status == "pending":
            # Update existing conflict with new snapshots
            existing.local_snapshot = local_snapshot
            existing.external_snapshot = external_snapshot
            await self.db.flush()
            return existing

        # Create new conflict
        return await self.conflict_repo.create(
            integration_id=integration_id,
            local_event_id=str(local_event.id),
            external_event_id=external_event.external_id,
            conflict_type=conflict_type,
            severity=severity,
            local_snapshot=local_snapshot,
            external_snapshot=external_snapshot,
        )

    def _determine_severity(
        self,
        conflict_type: str,
        local_event: CalendarEvent,
        external_event: ExternalEvent,
    ) -> str:
        """Determine conflict severity based on type and impact."""
        if conflict_type == "deleted_externally":
            return "high"

        if conflict_type == "updated_both":
            # Check if times are significantly different

            time_diff = abs((external_event.start_time - local_event.start_time).total_seconds())
            if time_diff > 3600:  # More than 1 hour
                return "high"
            return "medium"

        if conflict_type == "time_overlap":
            return "high"

        if conflict_type == "title_mismatch":
            return "low"

        return "medium"

    async def _find_existing_conflict(
        self,
        integration_id: str,
        local_event_id: str,
        external_event_id: str,
    ) -> SyncConflict | None:
        """Find existing pending conflict for these events."""
        from sqlalchemy import and_, select

        result = await self.db.execute(
            select(SyncConflict).where(
                and_(
                    SyncConflict.integration_id == integration_id,
                    SyncConflict.local_event_id == local_event_id,
                    SyncConflict.external_event_id == external_event_id,
                    SyncConflict.resolution_status == "pending",
                )
            )
        )
        return result.scalar_one_or_none()

    # ========================================================================
    # Conflict Resolution
    # ========================================================================

    async def resolve_conflict(
        self,
        conflict_id: str,
        strategy_name: str,
        resolved_by: str,
        custom_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ResolutionResult:
        """
        Resolve a conflict using the specified strategy.

        Args:
            conflict_id: The conflict ID
            strategy_name: Strategy to use (keep_local, keep_external, merge, etc.)
            resolved_by: User ID who is resolving
            custom_data: Optional custom data for merge strategy

        Returns:
            ResolutionResult indicating success/failure
        """
        # Get conflict
        conflict = await self.conflict_repo.get_by_id(conflict_id)
        if not conflict:
            return ResolutionResult(
                success=False,
                strategy=strategy_name,
                local_event_id="",
                external_event_id="",
                action_taken="",
                error_message=f"Conflict not found: {conflict_id}",
            )

        if conflict.resolution_status != "pending":
            return ResolutionResult(
                success=False,
                strategy=strategy_name,
                local_event_id=conflict.local_event_id,
                external_event_id=conflict.external_event_id,
                action_taken="",
                error_message=f"Conflict already resolved: {conflict.resolution_status}",
            )

        # Get strategy
        strategy = self.strategies.get(strategy_name)
        if not strategy:
            return ResolutionResult(
                success=False,
                strategy=strategy_name,
                local_event_id=conflict.local_event_id,
                external_event_id=conflict.external_event_id,
                action_taken="",
                error_message=f"Unknown strategy: {strategy_name}",
            )

        # Get integration to retrieve tenant_id for proper isolation
        from src.core.scheduling.integrations.repository import CalendarIntegrationRepository

        integration_repo = CalendarIntegrationRepository(self.db)
        integration = await integration_repo.get_by_id_any(conflict.integration_id)
        tenant_id = integration.tenant_id if integration else 0

        # Get local event with proper tenant isolation
        local_event = await self.event_repo.get_by_id(conflict.local_event_id, tenant_id=tenant_id)
        if not local_event:
            return ResolutionResult(
                success=False,
                strategy=strategy_name,
                local_event_id=conflict.local_event_id,
                external_event_id=conflict.external_event_id,
                action_taken="",
                error_message="Local event not found",
            )

        # Reconstruct external event from snapshot
        external_event = self._reconstruct_external_event(conflict.external_snapshot)

        # Apply strategy
        try:
            result = await strategy.resolve(
                local_event=local_event,
                external_event=external_event,
                local_data=conflict.local_snapshot,
                external_data=conflict.external_snapshot,
            )

            if result.success:
                # Mark conflict as resolved
                await self.conflict_repo.mark_resolved(
                    conflict_id=conflict_id,
                    strategy=strategy_name,
                    resolved_by=resolved_by,
                )
                await self.db.commit()

                logger.info(f"Conflict {conflict_id} resolved with strategy {strategy_name}")
            else:
                # Strategy couldn't auto-resolve
                result.error_message = result.error_message or "Strategy could not auto-resolve"

            return result

        except Exception as exc:
            logger.exception(f"Error resolving conflict {conflict_id}")
            await self.db.rollback()
            return ResolutionResult(
                success=False,
                strategy=strategy_name,
                local_event_id=conflict.local_event_id,
                external_event_id=conflict.external_event_id,
                action_taken="",
                error_message=str(exc),
            )

    def _reconstruct_external_event(self, snapshot: dict[str, Any]) -> ExternalEvent:  # TODO(TYPE): replace Any with concrete type
        """Reconstruct ExternalEvent from snapshot data."""

        return ExternalEvent(
            external_id=snapshot.get("external_event_id", ""),
            title=snapshot.get("title", ""),
            description=snapshot.get("description"),
            start_time=datetime.fromisoformat(snapshot["start_time"]),
            end_time=datetime.fromisoformat(snapshot["end_time"]),
            location=snapshot.get("location"),
            status=snapshot.get("status", "confirmed"),
        )

    async def auto_resolve_conflicts(
        self,
        integration_id: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Automatically resolve low-severity conflicts.

        Args:
            integration_id: Optional integration to limit scope

        Returns:
            Stats about resolved conflicts
        """
        # Get pending conflicts
        conflicts = await self.conflict_repo.list_pending(integration_id)

        resolved = 0
        failed = 0
        skipped = 0

        for conflict in conflicts:
            # Only auto-resolve low severity
            if conflict.severity != "low":
                skipped += 1
                continue

            # Use auto strategy
            result = await self.resolve_conflict(
                conflict_id=conflict.id,
                strategy_name="auto",
                resolved_by="system",
            )

            if result.success:
                resolved += 1
            else:
                failed += 1

        return {
            "total": len(conflicts),
            "resolved": resolved,
            "failed": failed,
            "skipped": skipped,
        }

    # ========================================================================
    # Conflict Querying
    # ========================================================================

    async def get_conflict_summary(
        self,
        integration_id: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get summary of conflicts for dashboard."""
        pending = await self.conflict_repo.list_pending(integration_id)

        by_severity = {"high": 0, "medium": 0, "low": 0}
        by_type: dict[str, int] = {}

        for conflict in pending:
            by_severity[conflict.severity] = by_severity.get(conflict.severity, 0) + 1
            by_type[conflict.conflict_type] = by_type.get(conflict.conflict_type, 0) + 1

        return {
            "total_pending": len(pending),
            "by_severity": by_severity,
            "by_type": by_type,
        }
