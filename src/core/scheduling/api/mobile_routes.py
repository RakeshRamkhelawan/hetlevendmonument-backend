"""
Mobile-optimized API endpoints for scheduling.

These endpoints are designed for mobile apps with:
- Optimized payload sizes
- Batch sync support
- Offline-first data structures
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.repository import CalendarEventRepository
from src.core.scheduling.schemas import (
    CalendarEventCreate,
    MobileQuickScheduleRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/mobile/scheduling",
    tags=["Mobile Scheduling"],
)


def get_event_repo(
    db: AsyncSession = Depends(get_db),
) -> CalendarEventRepository:
    """Dependency to get event repository."""
    return CalendarEventRepository(db)


# ========================================================================
# Mobile Calendar View
# ========================================================================


@router.get(
    "/calendar/view",
    response_model=dict,
    summary="Get mobile-optimized calendar view",
)
async def get_mobile_calendar_view(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    view_type: str = Query("week", description="day | 3day | week | month"),
    timezone: str = Query("UTC", description="Client timezone"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get optimized calendar view for mobile apps.

    Returns condensed event data optimized for mobile network usage.
    Payload size is kept under 100KB for week view.
    """
    # Convert dates to datetimes
    start_dt: datetime = datetime.combine(start_date, datetime.min.time())
    end_dt: datetime = datetime.combine(end_date, datetime.max.time())

    # Query events for the range
    result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.tenant_id == current_user.tenant_id,
                CalendarEvent.organizer_id == str(current_user.id),
                CalendarEvent.is_deleted.is_(False),
                CalendarEvent.start_time >= start_dt,
                CalendarEvent.end_time <= end_dt,
            )
        )
    )
    events: list[CalendarEvent] = list(result.scalars().all())

    # Build optimized response
    event_items: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
    all_day_events: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    for event in events:
        # Condensed event data
        event_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "id": event.id,
            "title": event.title,
            "start": event.start_time.isoformat(),
            "end": event.end_time.isoformat(),
            "all_day": event.is_all_day,
            "type": event.event_type,
            "status": event.status,
        }

        if event.is_all_day:
            all_day_events.append(event_data)
        else:
            event_items.append(event_data)

    return {
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "view_type": view_type,
        "timezone": timezone,
        "events": event_items,
        "all_day_events": all_day_events,
        "total_count": len(event_items) + len(all_day_events),
    }


# ========================================================================
# Batch Sync
# ========================================================================


@router.get(
    "/sync/batch",
    response_model=dict,
    summary="Get batch sync data",
)
async def get_batch_sync_data(
    last_sync: datetime | None = Query(None, description="Last sync timestamp (ISO format)"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get all changes since last sync for efficient mobile sync.

    Returns:
    - new_events: Events created since last_sync
    - updated_events: Events modified since last_sync
    - deleted_event_ids: Events soft-deleted since last_sync
    """
    now: datetime = datetime.now(timezone.utc)

    # If no last_sync provided, return last 7 days
    if last_sync is None:
        last_sync = now - timedelta(days=7)

    # Query for new events (created after last_sync)
    new_result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.tenant_id == current_user.tenant_id,
                CalendarEvent.organizer_id == str(current_user.id),
                CalendarEvent.created_at >= last_sync,
                CalendarEvent.is_deleted.is_(False),
            )
        )
    )
    new_events: list[CalendarEvent] = list(new_result.scalars().all())

    # Query for updated events (modified after last_sync but created before)
    updated_result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.tenant_id == current_user.tenant_id,
                CalendarEvent.organizer_id == str(current_user.id),
                CalendarEvent.updated_at >= last_sync,
                CalendarEvent.created_at < last_sync,
                CalendarEvent.is_deleted.is_(False),
            )
        )
    )
    updated_events: list[CalendarEvent] = list(updated_result.scalars().all())

    # Query for deleted events
    deleted_result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.tenant_id == current_user.tenant_id,
                CalendarEvent.organizer_id == str(current_user.id),
                CalendarEvent.updated_at >= last_sync,
                CalendarEvent.is_deleted.is_(True),
            )
        )
    )
    deleted_events: list[CalendarEvent] = list(deleted_result.scalars().all())

    def condense_event(event: CalendarEvent) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create minimal event representation."""
        return {
            "id": event.id,
            "title": event.title,
            "start": event.start_time.isoformat(),
            "end": event.end_time.isoformat(),
            "all_day": event.is_all_day,
            "type": event.event_type,
            "status": event.status,
            "location": event.location,
        }

    return {
        "sync_timestamp": now.isoformat(),
        "new_events": [condense_event(e) for e in new_events],
        "updated_events": [condense_event(e) for e in updated_events],
        "deleted_event_ids": [str(e.id) for e in deleted_events],
        "counts": {
            "new": len(new_events),
            "updated": len(updated_events),
            "deleted": len(deleted_events),
        },
    }


# ========================================================================
# Quick Schedule
# ========================================================================


@router.post(
    "/quick-schedule",
    response_model=dict,
    summary="Quick schedule with smart defaults",
)
async def quick_schedule(
    data: MobileQuickScheduleRequest,
    current_user: UserResponse = Depends(get_current_user),
    repo: CalendarEventRepository = Depends(get_event_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    One-tap scheduling with smart defaults.

    Automatically:
    - Suggests title based on participants
    - Finds next available slot
    - Sets reasonable duration (30 min default)
    """
    from src.core.scheduling.smart.service import SmartSchedulingService

    # Get smart scheduling service
    smart_service = SmartSchedulingService(repo.db)

    participants: list[str] = data.participants or []
    duration_minutes: int = data.duration_minutes

    # Auto-generate title from participants
    suggested_title: str
    if participants:
        suggested_title = f"Meeting with {', '.join(participants[:2])}"
        if len(participants) > 2:
            suggested_title += f" +{len(participants) - 2}"
    else:
        suggested_title = "Quick Meeting"

    title: str = data.title or suggested_title

    # Find next available slot
    preferred_date: date | None = data.preferred_date
    preferred_time: str | None = data.preferred_time

    start_time: datetime
    if preferred_date and preferred_time:
        # Use specified time
        start_time = datetime.fromisoformat(f"{preferred_date}T{preferred_time}")
    else:
        # Find next available slot
        suggestions = await smart_service.suggest_meeting_times(  # type: ignore[attr-defined]
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            duration_minutes=duration_minutes,
            days_ahead=7,
        )

        if not suggestions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No available slots found in the next 7 days",
            )

        start_time = suggestions[0].start_time

    end_time: datetime = start_time + timedelta(minutes=duration_minutes)

    # Create event
    event_data: CalendarEventCreate = CalendarEventCreate(
        title=title,
        description=data.description or "",
        start_time=start_time,
        end_time=end_time,
        location=data.location,
        event_type="meeting",
    )

    event = await repo.create(tenant_id=current_user.tenant_id, organizer_id=str(current_user.id), data=event_data)  # type: ignore

    await repo.db.commit()

    return {
        "success": True,
        "event_id": event.id,
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "participants": participants,
    }


# ========================================================================
# Quick Actions
# ========================================================================


@router.post(
    "/events/{event_id}/respond",
    response_model=dict,
    summary="Quick respond to meeting invite",
)
async def respond_to_invite(
    event_id: str,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    repo: CalendarEventRepository = Depends(get_event_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Quickly respond to a meeting invitation.

    Response: accept | decline | tentative
    """
    response: Any = data.get("response")  # TODO(TYPE): replace Any with concrete type
    if response not in ("accept", "decline", "tentative"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Response must be: accept, decline, or tentative",
        )

    event = await repo.get_by_id(event_id, current_user.tenant_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event not found: {event_id}",
        )

    # Update event status based on response
    if response == "accept":
        event.status = "confirmed"
    elif response == "decline":
        event.status = "cancelled"
    elif response == "tentative":
        event.status = "tentative"

    await repo.db.commit()

    return {
        "success": True,
        "event_id": event_id,
        "response": response,
        "status": event.status,
    }


@router.post(
    "/events/{event_id}/suggest-alternative",
    response_model=dict,
    summary="Suggest alternative time",
)
async def suggest_alternative_time(
    event_id: str,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    current_user: UserResponse = Depends(get_current_user),
    repo: CalendarEventRepository = Depends(get_event_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Suggest an alternative time for a meeting."""
    event = await repo.get_by_id(event_id, current_user.tenant_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event not found: {event_id}",
        )

    alternative_time: Any = data.get("alternative_time")  # TODO(TYPE): replace Any with concrete type
    if not alternative_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="alternative_time is required",
        )

    # Store suggestion in metadata
    if not event.metadata_json:
        event.metadata_json = {}

    event.metadata_json["alternative_time_suggestion"] = {
        "suggested_by": str(current_user.id),
        "suggested_at": datetime.now(timezone.utc).isoformat(),
        "alternative_time": alternative_time,
    }

    await repo.db.commit()

    return {
        "success": True,
        "event_id": event_id,
        "alternative_time": alternative_time,
    }


# ========================================================================
# Sync Status
# ========================================================================


@router.get(
    "/sync/status",
    response_model=dict,
    summary="Get sync status",
)
async def get_sync_status(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get sync status for mobile app.

    Returns counts of pending items to sync.
    """
    # Count pending conflicts
    from src.core.scheduling.webhooks.repository import SyncConflictRepository

    conflict_repo: SyncConflictRepository = SyncConflictRepository(db, current_user.tenant_id)
    pending_conflicts: list[Any] = await conflict_repo.list_pending(  # TODO(TYPE): replace Any with concrete type
        integration_id=None
    )  # All integrations

    # Count events modified recently
    recent: datetime = datetime.now(timezone.utc) - timedelta(hours=1)

    recent_result = await db.execute(
        select(CalendarEvent).where(
            and_(
                CalendarEvent.tenant_id == current_user.tenant_id,
                CalendarEvent.organizer_id == str(current_user.id),
                CalendarEvent.updated_at >= recent,
            )
        )
    )
    recent_changes: list[CalendarEvent] = list(recent_result.scalars().all())

    return {
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "pending_conflicts": len(pending_conflicts),
        "recent_changes": len(recent_changes),
        "needs_sync": len(pending_conflicts) > 0 or len(recent_changes) > 0,
    }
