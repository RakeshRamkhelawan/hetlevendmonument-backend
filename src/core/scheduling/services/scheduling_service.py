"""
Core scheduling service -- orchestrates the full scheduling flow.

Phase 0: direct service calls. No agent wrapper (deferred to Phase 1).
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.repository import (
    CalendarEventRepository,
    ConstraintRepository,
    PreferenceRepository,
    TimeBlockRepository,
)
from src.core.scheduling.schemas import (
    CalendarEventCreate,
    CalendarEventUpdate,
    SchedulingOption,
    SchedulingRequest,
    SchedulingResult,
)
from src.core.scheduling.services.conflict_service import ConflictDetectionService
from src.core.scheduling.services.constraint_service import ConstraintService
from src.core.scheduling.services.optimization_service import OptimizationService
from src.core.scheduling.services.slot_finder import SlotFinder

logger = logging.getLogger(__name__)


class SchedulingError(Exception):
    """Base exception for scheduling errors."""

    pass


class SchedulingService:
    """Core scheduling service with dependency injection."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.event_repo = CalendarEventRepository(db)
        self.block_repo = TimeBlockRepository(db)
        self.constraint_repo = ConstraintRepository(db)
        self.preference_repo = PreferenceRepository(db)
        self.conflict_service = ConflictDetectionService(self.event_repo, self.block_repo)
        self.constraint_service = ConstraintService(self.constraint_repo, self.preference_repo)
        self.optimization_service = OptimizationService()
        self.slot_finder = SlotFinder(self.conflict_service, self.preference_repo)

    # ------------------------------------------------------------------
    # Scheduling orchestration
    # ------------------------------------------------------------------

    async def schedule_meeting(
        self,
        request: SchedulingRequest,
        organizer_id: str,
        tenant_id: int,
    ) -> SchedulingResult:
        """Full scheduling flow: find slots -> pick best -> create event."""
        options = await self.slot_finder.find_slots(
            tenant_id=tenant_id,
            organizer_id=organizer_id,
            participant_ids=request.participants,
            duration_minutes=request.duration_minutes,
            earliest_start=request.earliest_start,
            latest_end=request.latest_end,
        )

        if not options:
            return SchedulingResult(
                success=False,
                message="No available time slots found in the given window.",
                alternatives=[],
            )

        best = self._select_best_option(options)

        event = CalendarEvent(
            tenant_id=tenant_id,
            title=request.title,
            description=request.description,
            start_time=best.start_time,
            end_time=best.end_time,
            organizer_id=organizer_id,
            participants=request.participants,
            event_type=request.event_type,
            priority=request.priority,
            location=request.location,
            recurrence_rule=(request.recurrence.to_rrule_string() if request.recurrence else None),
        )
        created = await self.event_repo.create(event)

        return SchedulingResult(
            success=True,
            event_id=created.id,
            selected_option=best,
            alternatives=options[1:],
            message="Meeting scheduled successfully.",
        )

    # ------------------------------------------------------------------
    # Direct CRUD
    # ------------------------------------------------------------------

    async def create_event(
        self,
        data: CalendarEventCreate,
        organizer_id: str,
        tenant_id: int,
    ) -> CalendarEvent:
        event = CalendarEvent(
            tenant_id=tenant_id,
            title=data.title,
            description=data.description,
            start_time=data.start_time,
            end_time=data.end_time,
            organizer_id=organizer_id,
            participants=data.participants,
            event_type=data.event_type,
            priority=data.priority,
            location=data.location,
            recurrence_rule=(data.recurrence.to_rrule_string() if data.recurrence else None),
        )
        return await self.event_repo.create(event)

    async def get_event(self, event_id: str, tenant_id: int) -> CalendarEvent | None:
        return await self.event_repo.get_by_id(event_id, tenant_id)

    async def list_events(
        self,
        tenant_id: int,
        user_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[CalendarEvent]:
        if start and end:
            return await self.event_repo.list_by_user_in_range(tenant_id, user_id, start, end)
        # Default: next 30 days
        now = datetime.now(tz=__import__("datetime").timezone.utc)
        from datetime import timedelta

        return await self.event_repo.list_by_user_in_range(
            tenant_id, user_id, now, now + timedelta(days=30)
        )

    async def update_event(
        self,
        event_id: str,
        tenant_id: int,
        data: CalendarEventUpdate,
    ) -> CalendarEvent | None:
        event = await self.event_repo.get_by_id(event_id, tenant_id)
        if not event:
            return None
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(event, field, value)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def cancel_event(self, event_id: str, tenant_id: int) -> bool:
        return await self.event_repo.soft_delete(event_id, tenant_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _select_best_option(
        options: list[SchedulingOption],
    ) -> SchedulingOption:
        """Select the best scheduling option by confidence score."""
        if not options:
            raise SchedulingError(
                "Cannot select from empty options list. " "No available slots were found."
            )
        return max(options, key=lambda o: o.confidence_score)
