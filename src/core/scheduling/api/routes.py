"""
REST API endpoints for scheduling.

Security: JWT auth via get_current_user on all endpoints.
Audit: State-changing operations are logged.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.middleware.rate_limiter import get_limiter
from src.core.scheduling.schemas import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
    PreferenceResponse,
    PreferenceUpdate,
    SchedulingRequest,
    SchedulingResult,
    TimeBlockCreate,
    TimeBlockResponse,
)
from src.core.scheduling.services.scheduling_service import SchedulingService
from src.core.security.security_manager import ThreatLevel
from src.core.governance.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduling", tags=["Scheduling"])
limiter = get_limiter(service_name="scheduling")


def _get_service(db: AsyncSession = Depends(get_db)) -> SchedulingService:
    return SchedulingService(db)


# -------------------------------------------------------------------------
# Scheduling orchestration
# -------------------------------------------------------------------------


@router.post(
    "/schedule",
    response_model=SchedulingResult,
    status_code=status.HTTP_200_OK,
    summary="Schedule a meeting (find best slot + book)",
)
@limiter.limit("20/minute")
async def schedule_meeting(
    request: Request,
    response: Response,
    body: SchedulingRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(_get_service),
) -> SchedulingResult:
    result = await service.schedule_meeting(
        request=body,
        organizer_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    if result.success:
        await AuditService.log_event(
            db=db,
            event_type="SCHEDULE_CREATED",
            severity=ThreatLevel.LOW,
            source_ip="internal",
            endpoint="/api/v1/scheduling/schedule",
            description=f"Meeting scheduled: {body.title}",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="CREATE",
            resource=f"calendar_event:{result.event_id}",
            metadata={"title": body.title, "duration": body.duration_minutes},
        )
    return result


# -------------------------------------------------------------------------
# Calendar event CRUD
# -------------------------------------------------------------------------


@router.post(
    "/events",
    response_model=CalendarEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a calendar event directly",
)
@limiter.limit("30/minute")
async def create_event(
    request: Request,
    response: Response,
    data: CalendarEventCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(_get_service),
) -> CalendarEventResponse:
    event = await service.create_event(
        data=data,
        organizer_id=str(current_user.id),
        tenant_id=current_user.tenant_id,
    )
    await AuditService.log_event(
        db=db,
        event_type="EVENT_CREATED",
        severity=ThreatLevel.LOW,
        source_ip="internal",
        endpoint="/api/v1/scheduling/events",
        description=f"Event created: {data.title}",
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="CREATE",
        resource=f"calendar_event:{event.id}",
    )
    return CalendarEventResponse.model_validate(event)


@router.get(
    "/events",
    response_model=list[CalendarEventResponse],
    summary="List events for the current user",
)
@limiter.limit("60/minute")
async def list_events(
    request: Request,
    response: Response,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> list[CalendarEventResponse]:
    events = await service.list_events(
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
        start=start_date,
        end=end_date,
    )
    return [CalendarEventResponse.model_validate(e) for e in events]


@router.get(
    "/events/{event_id}",
    response_model=CalendarEventResponse,
)
@limiter.limit("60/minute")
async def get_event(
    request: Request,
    response: Response,
    event_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> CalendarEventResponse:
    event = await service.get_event(event_id, current_user.tenant_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    return CalendarEventResponse.model_validate(event)


@router.patch(
    "/events/{event_id}",
    response_model=CalendarEventResponse,
)
@limiter.limit("30/minute")
async def update_event(
    request: Request,
    response: Response,
    event_id: str,
    data: CalendarEventUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(_get_service),
) -> CalendarEventResponse:
    event = await service.update_event(
        event_id=event_id,
        tenant_id=current_user.tenant_id,
        data=data,
    )
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    await AuditService.log_event(
        db=db,
        event_type="EVENT_UPDATED",
        severity=ThreatLevel.LOW,
        source_ip="internal",
        endpoint=f"/api/v1/scheduling/events/{event_id}",
        description=f"Event updated: {event_id}",
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="UPDATE",
        resource=f"calendar_event:{event_id}",
        metadata=data.model_dump(exclude_unset=True),
    )
    return CalendarEventResponse.model_validate(event)


@router.delete(
    "/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@limiter.limit("30/minute")
async def cancel_event(
    request: Request,
    response: Response,
    event_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    service: SchedulingService = Depends(_get_service),
) -> None:
    deleted = await service.cancel_event(event_id, current_user.tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    await AuditService.log_event(
        db=db,
        event_type="EVENT_CANCELLED",
        severity=ThreatLevel.LOW,
        source_ip="internal",
        endpoint=f"/api/v1/scheduling/events/{event_id}",
        description=f"Event cancelled: {event_id}",
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action="DELETE",
        resource=f"calendar_event:{event_id}",
    )


# -------------------------------------------------------------------------
# Time blocks
# -------------------------------------------------------------------------


@router.post(
    "/time-blocks",
    response_model=TimeBlockResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a time block (focus time)",
)
@limiter.limit("30/minute")
async def create_time_block(
    request: Request,
    response: Response,
    data: TimeBlockCreate,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> TimeBlockResponse:
    from src.core.scheduling.models import TimeBlock

    block = TimeBlock(
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
        block_type=data.block_type,
        start_time=data.start_time,
        end_time=data.end_time,
        recurrence_rule=(data.recurrence.to_rrule_string() if data.recurrence else None),
        is_hard_block=data.is_hard_block,
        label=data.label,
    )
    created = await service.block_repo.create(block)
    return TimeBlockResponse.model_validate(created)


@router.get(
    "/time-blocks",
    response_model=list[TimeBlockResponse],
    summary="List time blocks for the current user",
)
@limiter.limit("60/minute")
async def list_time_blocks(
    request: Request,
    response: Response,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> list[TimeBlockResponse]:
    from datetime import timedelta
    from datetime import timezone as tz

    start = start_date or datetime.now(tz=tz.utc)
    end = end_date or (start + timedelta(days=30))
    blocks = await service.block_repo.list_by_user_in_range(
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
        start=start,
        end=end,
    )
    return [TimeBlockResponse.model_validate(b) for b in blocks]


@router.delete(
    "/time-blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
@limiter.limit("30/minute")
async def delete_time_block(
    request: Request,
    response: Response,
    block_id: str,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> None:
    deleted = await service.block_repo.soft_delete(block_id, current_user.tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Time block not found",
        )


# -------------------------------------------------------------------------
# Preferences
# -------------------------------------------------------------------------


@router.get(
    "/preferences",
    response_model=Optional[PreferenceResponse],
    summary="Get scheduling preferences for the current user",
)
@limiter.limit("60/minute")
async def get_preferences(
    request: Request,
    response: Response,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> PreferenceResponse | None:
    pref = await service.preference_repo.get_by_user(current_user.tenant_id, str(current_user.id))
    if not pref:
        return None
    return PreferenceResponse.model_validate(pref)


@router.put(
    "/preferences",
    response_model=PreferenceResponse,
    summary="Create or update scheduling preferences",
)
@limiter.limit("30/minute")
async def upsert_preferences(
    request: Request,
    response: Response,
    data: PreferenceUpdate,
    current_user: UserResponse = Depends(get_current_user),
    service: SchedulingService = Depends(_get_service),
) -> PreferenceResponse:
    from src.core.scheduling.models import SchedulingPreference

    pref = SchedulingPreference(
        tenant_id=current_user.tenant_id,
        user_id=str(current_user.id),
        timezone_name=data.timezone_name or "UTC",
        working_hours_start=data.working_hours_start,
        working_hours_end=data.working_hours_end,
        preferred_duration_minutes=data.preferred_duration_minutes or 30,
        buffer_minutes=data.buffer_minutes or 5,
        preferences_json=data.preferences_json,
    )
    result = await service.preference_repo.upsert(pref)
    return PreferenceResponse.model_validate(result)
