"""
Repository pattern for scheduling data access.

Every query MUST include tenant_id filtering for multi-tenant isolation.
Conflict detection uses SQL-based overlap queries (indexed).
"""

from datetime import datetime
from typing import Optional
from collections.abc import Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.models import (
    CalendarEvent,
    SchedulingConstraint,
    SchedulingPreference,
    TimeBlock,
)


class CalendarEventRepository:
    """Repository for CalendarEvent with mandatory tenant isolation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, event_id: str, tenant_id: int) -> CalendarEvent | None:
        result = await self.db.execute(
            select(CalendarEvent).where(
                and_(
                    CalendarEvent.id == event_id,
                    CalendarEvent.tenant_id == tenant_id,
                    CalendarEvent.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user_in_range(
        self,
        tenant_id: int,
        user_id: str,
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        result = await self.db.execute(
            select(CalendarEvent)
            .where(
                and_(
                    CalendarEvent.tenant_id == tenant_id,
                    CalendarEvent.organizer_id == user_id,
                    CalendarEvent.start_time < end,
                    CalendarEvent.end_time > start,
                    CalendarEvent.is_deleted.is_(False),
                )
            )
            .order_by(CalendarEvent.start_time)
        )
        return list(result.scalars().all())

    async def list_by_tenant_in_range(
        self,
        tenant_id: int,
        start: datetime,
        end: datetime,
    ) -> list[CalendarEvent]:
        result = await self.db.execute(
            select(CalendarEvent)
            .where(
                and_(
                    CalendarEvent.tenant_id == tenant_id,
                    CalendarEvent.start_time < end,
                    CalendarEvent.end_time > start,
                    CalendarEvent.is_deleted.is_(False),
                )
            )
            .order_by(CalendarEvent.start_time)
        )
        return list(result.scalars().all())

    async def find_overlapping(
        self,
        tenant_id: int,
        user_id: str,
        start: datetime,
        end: datetime,
        exclude_event_id: str | None = None,
    ) -> list[CalendarEvent]:
        """Find events that overlap with the given time range.

        Uses SQL range overlap: existing.start < new.end AND existing.end > new.start.
        The composite index on (tenant_id, start_time, end_time) makes this O(log n).
        """
        conditions = [
            CalendarEvent.tenant_id == tenant_id,
            CalendarEvent.organizer_id == user_id,
            CalendarEvent.start_time < end,
            CalendarEvent.end_time > start,
            CalendarEvent.is_deleted.is_(False),
            CalendarEvent.status != "cancelled",
        ]
        if exclude_event_id:
            conditions.append(CalendarEvent.id != exclude_event_id)

        result = await self.db.execute(select(CalendarEvent).where(and_(*conditions)))
        return list(result.scalars().all())

    async def find_participant_overlapping(
        self,
        tenant_id: int,
        participant_ids: list[str],
        start: datetime,
        end: datetime,
        exclude_event_id: str | None = None,
    ) -> list[CalendarEvent]:
        """Find events where any participant has a conflict."""
        conditions = [
            CalendarEvent.tenant_id == tenant_id,
            CalendarEvent.start_time < end,
            CalendarEvent.end_time > start,
            CalendarEvent.is_deleted.is_(False),
            CalendarEvent.status != "cancelled",
            or_(
                CalendarEvent.organizer_id.in_(participant_ids),
            ),
        ]
        if exclude_event_id:
            conditions.append(CalendarEvent.id != exclude_event_id)

        result = await self.db.execute(select(CalendarEvent).where(and_(*conditions)))
        return list(result.scalars().all())

    async def create(self, event: CalendarEvent) -> CalendarEvent:
        self.db.add(event)
        await self.db.flush()
        return event

    async def bulk_create(
        self, events: Sequence[CalendarEvent], batch_size: int = 100
    ) -> list[CalendarEvent]:
        """Create multiple events in batches for performance.

        Args:
            events: Sequence of events to create
            batch_size: Number of events per batch (default 100)

        Returns:
            List of created events
        """
        created: list[CalendarEvent] = []
        for i in range(0, len(events), batch_size):
            batch = events[i : i + batch_size]
            for event in batch:
                self.db.add(event)
            await self.db.flush()
            created.extend(batch)
        return created

    async def bulk_upsert(
        self,
        events: Sequence[CalendarEvent],
        tenant_id: int,
        batch_size: int = 100,
    ) -> dict[str, int]:
        """Bulk upsert events based on external_id in metadata.

        Args:
            events: Sequence of events to upsert
            tenant_id: Tenant ID for filtering
            batch_size: Number of events per batch

        Returns:
            Dict with counts: created, updated, unchanged
        """

        result = {"created": 0, "updated": 0, "unchanged": 0}

        # For each event, check if it exists by external_id
        for event in events:
            external_id = event.metadata_json.get("external_id") if event.metadata_json else None

            if external_id:
                # Check for existing event
                existing = await self.db.execute(
                    select(CalendarEvent).where(
                        and_(
                            CalendarEvent.tenant_id == tenant_id,
                            CalendarEvent.metadata_json["external_id"].as_string() == external_id,
                            CalendarEvent.is_deleted.is_(False),
                        )
                    )
                )
                existing_event = existing.scalar_one_or_none()

                if existing_event:
                    # Update existing
                    existing_event.title = event.title
                    existing_event.description = event.description
                    existing_event.start_time = event.start_time
                    existing_event.end_time = event.end_time
                    existing_event.location = event.location
                    existing_event.metadata_json = event.metadata_json
                    result["updated"] += 1
                else:
                    # Create new
                    self.db.add(event)
                    result["created"] += 1
            else:
                # No external_id, create as new
                self.db.add(event)
                result["created"] += 1

            if (result["created"] + result["updated"]) % batch_size == 0:
                await self.db.flush()

        await self.db.flush()
        return result

    async def soft_delete(self, event_id: str, tenant_id: int) -> bool:
        event = await self.get_by_id(event_id, tenant_id)
        if not event:
            return False
        event.soft_delete()
        event.status = "cancelled"
        await self.db.flush()
        return True


class TimeBlockRepository:
    """Repository for TimeBlock with tenant isolation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, block_id: str, tenant_id: int) -> TimeBlock | None:
        result = await self.db.execute(
            select(TimeBlock).where(
                and_(
                    TimeBlock.id == block_id,
                    TimeBlock.tenant_id == tenant_id,
                    TimeBlock.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user_in_range(
        self,
        tenant_id: int,
        user_id: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeBlock]:
        result = await self.db.execute(
            select(TimeBlock)
            .where(
                and_(
                    TimeBlock.tenant_id == tenant_id,
                    TimeBlock.user_id == user_id,
                    TimeBlock.start_time < end,
                    TimeBlock.end_time > start,
                    TimeBlock.is_deleted.is_(False),
                )
            )
            .order_by(TimeBlock.start_time)
        )
        return list(result.scalars().all())

    async def find_hard_blocks_in_range(
        self,
        tenant_id: int,
        user_id: str,
        start: datetime,
        end: datetime,
    ) -> list[TimeBlock]:
        result = await self.db.execute(
            select(TimeBlock)
            .where(
                and_(
                    TimeBlock.tenant_id == tenant_id,
                    TimeBlock.user_id == user_id,
                    TimeBlock.is_hard_block.is_(True),
                    TimeBlock.start_time < end,
                    TimeBlock.end_time > start,
                    TimeBlock.is_deleted.is_(False),
                )
            )
            .order_by(TimeBlock.start_time)
        )
        return list(result.scalars().all())

    async def create(self, block: TimeBlock) -> TimeBlock:
        self.db.add(block)
        await self.db.flush()
        return block

    async def soft_delete(self, block_id: str, tenant_id: int) -> bool:
        block = await self.get_by_id(block_id, tenant_id)
        if not block:
            return False
        block.soft_delete()
        await self.db.flush()
        return True


class ConstraintRepository:
    """Repository for SchedulingConstraint with tenant isolation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_user(self, tenant_id: int, user_id: str) -> list[SchedulingConstraint]:
        result = await self.db.execute(
            select(SchedulingConstraint).where(
                and_(
                    SchedulingConstraint.tenant_id == tenant_id,
                    SchedulingConstraint.user_id == user_id,
                    SchedulingConstraint.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())

    async def list_hard_constraints(
        self, tenant_id: int, user_id: str
    ) -> list[SchedulingConstraint]:
        result = await self.db.execute(
            select(SchedulingConstraint).where(
                and_(
                    SchedulingConstraint.tenant_id == tenant_id,
                    SchedulingConstraint.user_id == user_id,
                    SchedulingConstraint.is_hard.is_(True),
                    SchedulingConstraint.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())


class PreferenceRepository:
    """Repository for SchedulingPreference with tenant isolation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_user(self, tenant_id: int, user_id: str) -> SchedulingPreference | None:
        result = await self.db.execute(
            select(SchedulingPreference).where(
                and_(
                    SchedulingPreference.tenant_id == tenant_id,
                    SchedulingPreference.user_id == user_id,
                    SchedulingPreference.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def upsert(self, preference: SchedulingPreference) -> SchedulingPreference:
        existing = await self.get_by_user(preference.tenant_id, preference.user_id)
        if existing:
            for field in (
                "timezone_name",
                "working_hours_start",
                "working_hours_end",
                "preferred_duration_minutes",
                "buffer_minutes",
                "preferences_json",
            ):
                val = getattr(preference, field)
                if val is not None:
                    setattr(existing, field, val)
            await self.db.flush()
            return existing
        self.db.add(preference)
        await self.db.flush()
        return preference
