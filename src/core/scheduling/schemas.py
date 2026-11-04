"""
Pydantic v2 schemas for scheduling API request/response validation.

These are for the API layer only -- not for database models.
"""

import re
from datetime import date, datetime, time, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from typing import TypedDict

# RFC 5545 weekday codes (optionally prefixed by ordinal -4..4, excluding 0)
_BYDAY_RE = re.compile(r"^(-?[1-4])?(?:MO|TU|WE|TH|FR|SA|SU)$")


class RRULEKwargs(TypedDict, total=False):
    """Keyword arguments accepted by ``RecurrencePattern.from_rrule_string``."""

    freq: str
    interval: int
    count: int
    until: datetime
    byday: list[str]
    bymonthday: list[int]


class RecurrencePattern(BaseModel):
    """RFC 5545 iCalendar RRULE subset."""

    freq: Literal["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]
    interval: int = Field(default=1, ge=1, le=365)
    count: int | None = Field(default=None, ge=1, le=999)
    until: datetime | None = None
    byday: list[str] | None = None
    bymonthday: list[int] | None = None

    @field_validator("byday")
    @classmethod
    def _validate_byday(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for day in v:
            if not _BYDAY_RE.match(day):
                raise ValueError(
                    f"Invalid BYDAY value '{day}'. "
                    "Must be a weekday code (MO TU WE TH FR SA SU) "
                    "optionally preceded by an ordinal 1-4 or -1 to -4."
                )
        return v

    def to_rrule_string(self) -> str:
        parts = [f"FREQ={self.freq}"]
        if self.interval != 1:
            parts.append(f"INTERVAL={self.interval}")
        if self.count is not None:
            parts.append(f"COUNT={self.count}")
        if self.until is not None:
            parts.append(f"UNTIL={self.until.strftime('%Y%m%dT%H%M%SZ')}")
        if self.byday:
            parts.append(f"BYDAY={','.join(self.byday)}")
        if self.bymonthday:
            parts.append(f"BYMONTHDAY={','.join(str(d) for d in self.bymonthday)}")
        return ";".join(parts)

    @classmethod
    def from_rrule_string(cls, rrule: str) -> "RecurrencePattern":
        """Parse an RFC 5545 RRULE string into a RecurrencePattern.

        Accepts both bare RRULE strings (``FREQ=WEEKLY``) and
        property-prefixed strings (``RRULE:FREQ=WEEKLY``).

        Raises:
            ValueError: If the RRULE string is invalid or missing required components.
        """
        import logging

        logger = logging.getLogger(__name__)

        try:
            # Strip optional "RRULE:" property prefix
            stripped = rrule.strip()
            if stripped.upper().startswith("RRULE:"):
                stripped = stripped[6:]

            if not stripped:
                raise ValueError("RRULE string is empty")

            parts: dict[str, str] = {}
            for token in stripped.split(";"):
                if not token:
                    continue
                if "=" not in token:
                    logger.warning(f"Skipping invalid RRULE token: {token}")
                    continue
                key, _, value = token.partition("=")
                if not key or not value:
                    logger.warning(f"Skipping malformed RRULE token: {token}")
                    continue
                parts[key.upper()] = value

            if "FREQ" not in parts:
                raise ValueError("RRULE string must contain FREQ component")

            kwargs: RRULEKwargs = {"freq": parts["FREQ"].upper()}

            if "INTERVAL" in parts:
                try:
                    kwargs["interval"] = int(parts["INTERVAL"])
                except ValueError as e:
                    raise ValueError(f"Invalid INTERVAL value: {parts['INTERVAL']}") from e

            if "COUNT" in parts:
                try:
                    kwargs["count"] = int(parts["COUNT"])
                except ValueError as e:
                    raise ValueError(f"Invalid COUNT value: {parts['COUNT']}") from e

            if "UNTIL" in parts:
                raw = parts["UNTIL"]
                try:
                    # Parse basic date/datetime: YYYYMMDD or YYYYMMDDTHHMMSSz
                    if len(raw) == 8:
                        kwargs["until"] = datetime.strptime(raw, "%Y%m%d").replace(
                            tzinfo=timezone.utc
                        )
                    else:
                        kwargs["until"] = datetime.strptime(
                            raw.rstrip("Z"), "%Y%m%dT%H%M%S"
                        ).replace(tzinfo=timezone.utc)
                except ValueError as e:
                    raise ValueError(f"Invalid UNTIL date format: {raw}") from e

            if "BYDAY" in parts:
                kwargs["byday"] = [d.strip() for d in parts["BYDAY"].split(",") if d.strip()]

            if "BYMONTHDAY" in parts:
                try:
                    kwargs["bymonthday"] = [
                        int(d) for d in parts["BYMONTHDAY"].split(",") if d.strip()
                    ]
                except ValueError as e:
                    raise ValueError(f"Invalid BYMONTHDAY value: {parts['BYMONTHDAY']}") from e

            return cls(**kwargs)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error parsing RRULE '{rrule}': {e}")
            raise ValueError(f"Failed to parse RRULE string: {rrule}") from e


class SchedulingRequest(BaseModel):
    """Request for scheduling a meeting."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    duration_minutes: int = Field(..., ge=5, le=480)
    participants: list[str] = Field(..., min_length=1, max_length=50)
    earliest_start: datetime
    latest_end: datetime
    priority: int = Field(default=3, ge=1, le=9)
    location: str | None = Field(default=None, max_length=500)
    event_type: str = Field(default="meeting", max_length=50)
    recurrence: RecurrencePattern | None = None
    constraints: dict[str, str | int | float | bool | list[str] | None] | None = Field(default=None)

    @field_validator("latest_end")
    @classmethod
    def _end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("earliest_start")
        if start and v <= start:
            raise ValueError("latest_end must be after earliest_start")
        return v


class SchedulingOption(BaseModel):
    """A possible scheduling option with score."""

    start_time: datetime
    end_time: datetime
    confidence_score: float = Field(ge=0.0, le=1.0)
    conflicts: list[str] = Field(default_factory=list)
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class SchedulingResult(BaseModel):
    """Result of scheduling optimisation."""

    success: bool
    event_id: str | None = None
    selected_option: SchedulingOption | None = None
    alternatives: list[SchedulingOption] = Field(default_factory=list)
    message: str = ""
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class CalendarEventCreate(BaseModel):
    """Schema for creating a calendar event directly."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    start_time: datetime
    end_time: datetime
    location: str | None = Field(default=None, max_length=500)
    participants: list[str] | None = Field(default=None)
    event_type: str = Field(default="meeting", max_length=50)
    priority: int = Field(default=3, ge=1, le=9)
    recurrence: RecurrencePattern | None = None

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class CalendarEventUpdate(BaseModel):
    """Schema for partial update of a calendar event."""

    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    start_time: datetime | None = None
    end_time: datetime | None = None
    location: str | None = Field(default=None, max_length=500)
    participants: list[str] | None = None
    event_type: str | None = Field(default=None, max_length=50)
    priority: int | None = Field(default=None, ge=1, le=9)
    status: str | None = Field(default=None, max_length=50)


class CalendarEventResponse(BaseModel):
    """API response for a calendar event."""

    id: str
    tenant_id: int
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    location: str | None = None
    organizer_id: str
    participants: list[str] | None = None
    event_type: str
    status: str
    priority: int
    recurrence_rule: str | None = None
    metadata_json: dict[str, str | int | float | bool | None] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TimeBlockCreate(BaseModel):
    """Schema for creating a time block."""

    block_type: str = Field(default="focus_time", max_length=50)
    start_time: datetime
    end_time: datetime
    recurrence: RecurrencePattern | None = None
    is_hard_block: bool = True
    label: str | None = Field(default=None, max_length=255)

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, v: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start_time")
        if start and v <= start:
            raise ValueError("end_time must be after start_time")
        return v


class TimeBlockResponse(BaseModel):
    """API response for a time block."""

    id: str
    tenant_id: int
    user_id: str
    block_type: str
    start_time: datetime
    end_time: datetime
    recurrence_rule: str | None = None
    is_hard_block: bool
    label: str | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PreferenceUpdate(BaseModel):
    """Schema for updating scheduling preferences."""

    timezone_name: str | None = Field(default=None, max_length=100)
    working_hours_start: time | None = None
    working_hours_end: time | None = None
    preferred_duration_minutes: int | None = Field(default=None, ge=5, le=480)
    buffer_minutes: int | None = Field(default=None, ge=0, le=60)
    preferences_json: dict[str, str | int | float | bool | None] | None = None


class PreferenceResponse(BaseModel):
    """API response for scheduling preferences."""

    id: str
    tenant_id: int
    user_id: str
    timezone_name: str
    working_hours_start: time | None = None
    working_hours_end: time | None = None
    preferred_duration_minutes: int
    buffer_minutes: int
    preferences_json: dict[str, str | int | float | bool | None] | None = None

    model_config = ConfigDict(from_attributes=True)


class ConflictInfo(BaseModel):
    """Info about a detected scheduling conflict."""

    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    severity: Literal["hard", "soft"]


# -- Calendar Integration Schemas (Phase 1) --------------------------


class CalendarIntegrationResponse(BaseModel):
    """API response for a calendar integration."""

    id: str
    provider: str
    provider_account_id: str
    provider_calendar_id: str
    is_active: bool
    last_synced_at: datetime | None = None
    token_expires_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ConnectProviderRequest(BaseModel):
    """Request body for initiating an OAuth connection."""

    provider: Literal["google", "outlook"]
    redirect_uri: str = Field(..., max_length=500)


class OAuthCallbackRequest(BaseModel):
    """Request body for completing an OAuth callback."""

    code: str = Field(..., min_length=1, max_length=2048)
    redirect_uri: str = Field(..., max_length=500)


class SyncStatusResponse(BaseModel):
    """Response after triggering a sync."""

    integration_id: str
    provider: str
    created: int = 0
    updated: int = 0
    deleted: int = 0
    errors: list[str] = Field(default_factory=list)
    next_sync_token: str | None = None


# ========================================================================
# Conflict Resolution Schemas (Phase 4A)
# ========================================================================


class ConflictItem(BaseModel):
    """A single conflict item in the list."""

    id: str
    integration_id: str
    local_event_id: str
    external_event_id: str
    conflict_type: str  # time_overlap | title_mismatch | deleted_externally | updated_both
    severity: str  # high | medium | low
    local_snapshot: dict[str, str | int | float | bool | datetime | None]
    external_snapshot: dict[str, str | int | float | bool | datetime | None]
    resolution_status: str
    created_at: datetime


class ConflictListResponse(BaseModel):
    """Response for listing conflicts."""

    conflicts: list[ConflictItem]
    total: int


class ConflictSummaryResponse(BaseModel):
    """Summary statistics for conflicts."""

    total_pending: int
    by_severity: dict[str, int]
    by_type: dict[str, int]


class ConflictResolutionRequest(BaseModel):
    """Request to resolve a conflict."""

    strategy: str = Field(
        ...,
        description="Resolution strategy: keep_local, keep_external, merge, auto",
    )
    custom_data: dict[str, str | int | float | bool | list[str] | None] | None = None


class ConflictResolutionResponse(BaseModel):
    """Response after resolving a conflict."""

    success: bool
    conflict_id: str
    strategy: str
    action_taken: str
    error_message: str | None = None


# ========================================================================
# Partner Program Schemas (Phase 4B)
# ========================================================================


class PartnerCreateRequest(BaseModel):
    """Request to create a design partner."""

    name: str = Field(..., min_length=1, max_length=255)
    industry: str = Field(..., min_length=1, max_length=50)
    contact_email: str = Field(..., max_length=255)
    contact_name: str | None = Field(None, max_length=255)
    start_date: datetime
    end_date: datetime
    max_users: int = Field(default=100, ge=1, le=10000)
    allowed_features: list[str] | None = None


class PartnerResponse(BaseModel):
    """Response for partner data."""

    id: str
    tenant_id: int
    name: str
    industry: str
    contact_email: str
    contact_name: str | None
    status: str
    start_date: datetime
    end_date: datetime
    max_users: int
    allowed_features: list[str]
    metrics: dict[str, int]

    model_config = ConfigDict(from_attributes=True)


class FeedbackCreateRequest(BaseModel):
    """Request to submit partner feedback."""

    feedback_type: str = Field(
        ..., pattern="^(bug|feature_request|usability|performance|security|other)$"
    )
    severity: str = Field(..., pattern="^(critical|high|medium|low)$")
    category: str = Field(..., pattern="^(ui|api|integration|performance|security|documentation)$")
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    reproduction_steps: str | None = None
    expected_behavior: str | None = None
    actual_behavior: str | None = None
    environment: dict[str, str | int | float | bool | None] | None = None


class FeedbackResponse(BaseModel):
    """Response for feedback data."""

    id: str
    partner_id: str
    title: str
    feedback_type: str
    severity: str
    category: str
    status: str
    priority: int
    created_at: datetime
    assigned_to: str | None

    model_config = ConfigDict(from_attributes=True)


# ========================================================================
# Voice UI Schemas (Phase 4D)
# ========================================================================


class VoiceProcessRequest(BaseModel):
    """Request to process voice input."""

    transcript: str = Field(..., min_length=1, max_length=1000, description="Speech-to-text result")
    session_id: str | None = None
    timezone: str = Field(default="UTC", max_length=50)


class VoiceProcessResponse(BaseModel):
    """Response after processing voice input."""

    response_text: str
    action_taken: str
    requires_follow_up: bool
    session_id: str
    data: dict[str, str | int | float | bool | list[str] | None] | None = None
    suggested_responses: list[str] | None = None


class VoiceConfirmRequest(BaseModel):
    """Request to confirm a pending voice action."""

    session_id: str = Field(..., min_length=1)
    confirmed: bool


# ========================================================================
# Mobile API Schemas (Phase 4C)
# ========================================================================


class MobileCalendarViewRequest(BaseModel):
    """Request for mobile calendar view."""

    start_date: date
    end_date: date
    view_type: str = Field(default="week", pattern="^(day|3day|week|month)$")
    timezone: str = Field(default="UTC", max_length=50)


class MobileQuickScheduleRequest(BaseModel):
    """Request for quick schedule."""

    participants: list[str] | None = None
    duration_minutes: int = Field(default=30, ge=5, le=480)
    preferred_date: date | None = None
    preferred_time: str | None = None
    title: str | None = Field(None, max_length=255)
    description: str | None = None
    location: str | None = None


class MobileRespondRequest(BaseModel):
    """Request to respond to meeting invite."""

    response: str = Field(..., pattern="^(accept|decline|tentative)$")


# ========================================================================
# Pagination Schema
# ========================================================================


class PaginatedResponse(BaseModel):
    """Base class for paginated responses."""

    items: list[Any]  # TODO(TYPE): replace Any with concrete type
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_prev: bool
