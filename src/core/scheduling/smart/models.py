"""Data models for Smart Scheduling Intelligence.

Contains database models and Pydantic schemas for:
- User scheduling preferences
- Availability patterns
- Smart scheduling requests/responses
"""

import uuid
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class Chronotype(str, Enum):
    """User chronotype - preferred working hours."""

    MORNING = "morning"
    EVENING = "evening"
    NEUTRAL = "neutral"


class EventStatus(str, Enum):
    """Calendar event status for pattern analysis."""

    BUSY = "busy"
    TENTATIVE = "tentative"
    FREE = "free"


class ResolutionStrategy(str, Enum):
    """Conflict resolution strategies."""

    ADJACENT = "adjacent"
    ALTERNATIVE_DAY = "alternative_day"
    SHORTER_DURATION = "shorter"
    VIRTUAL = "virtual"
    ASYNC = "async"


class UserSchedulingProfile(Base):  # type: ignore[misc]
    """Extended user preferences for smart scheduling.

    Stores ML-derived insights and user preferences for
    intelligent meeting scheduling.
    """

    __tablename__ = "user_scheduling_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    # GEEN `unique=True` op user_id alleen (Gate 2-review 2026-08-17). Deze tabel is
    # tenant-gescheiden, dus een globaal unieke index betekent twee dingen: tenant B kan
    # geen profiel aanmaken voor een user_id die tenant A al gebruikt (de insert faalt op
    # een rij die B niet mag zien), en het verschil tussen "aangemaakt" en "unique
    # violation" verraadt het BESTAAN van een gebruiker in een andere tenant. De juiste
    # vorm staat elf regels verderop in dezelfde domeinfamilie:
    # `uq_calendar_integration_user_provider UNIQUE (tenant_id, user_id, provider)`.
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Chronotype preference
    chronotype: Mapped[str] = mapped_column(
        String(20),
        default=Chronotype.NEUTRAL.value,
    )

    # Preferred meeting times (user can set preferred windows)
    preferred_morning_start: Mapped[time | None] = mapped_column(
        Time(timezone=True),
        nullable=True,
    )
    preferred_morning_end: Mapped[time | None] = mapped_column(
        Time(timezone=True),
        nullable=True,
    )
    preferred_afternoon_start: Mapped[time | None] = mapped_column(
        Time(timezone=True),
        nullable=True,
    )
    preferred_afternoon_end: Mapped[time | None] = mapped_column(
        Time(timezone=True),
        nullable=True,
    )

    # Focus time preferences
    focus_time_min_duration: Mapped[int] = mapped_column(
        Integer,
        default=120,
        nullable=False,
    )
    protect_focus_time: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    # Buffer preferences (in minutes)
    default_prep_buffer: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    default_recovery_buffer: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )
    travel_buffer_minutes: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    # Meeting limits
    max_meetings_per_day: Mapped[int] = mapped_column(
        Integer,
        default=6,
        nullable=False,
    )
    max_consecutive_meetings: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    # User's timezone for accurate calculations
    timezone: Mapped[str] = mapped_column(
        String(50),
        default="UTC",
        nullable=False,
    )

    # ML-derived data
    last_pattern_analysis: Mapped[datetime | None] = mapped_column(
        nullable=True,
    )
    pattern_confidence: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "focus_time_min_duration >= 30 AND focus_time_min_duration <= 480",
            name="chk_focus_duration_range",
        ),
        CheckConstraint(
            "max_meetings_per_day >= 1 AND max_meetings_per_day <= 20",
            name="chk_meetings_range",
        ),
        CheckConstraint(
            "max_consecutive_meetings >= 1 AND max_consecutive_meetings <= 10",
            name="chk_consecutive_range",
        ),
        # Uniek BINNEN de tenant, niet globaal (Gate 2-review 2026-08-17). Zie de
        # toelichting bij `user_id` hierboven.
        UniqueConstraint("tenant_id", "user_id", name="uq_scheduling_profile_tenant_user"),
    )

    @validates("chronotype")
    def validate_chronotype(self, key: str, value: str) -> str:
        """Validate chronotype value."""
        allowed = [c.value for c in Chronotype]
        if value not in allowed:
            raise ValueError(f"Invalid chronotype: {value}. Must be one of {allowed}")
        return value

    @validates("timezone")
    def validate_timezone(self, key: str, value: str) -> str:
        """Validate timezone string."""
        import pytz

        if value not in pytz.all_timezones:
            raise ValueError(f"Invalid timezone: {value}")
        return value

    def __repr__(self) -> str:
        return (
            f"<UserSchedulingProfile("
            f"user_id={self.user_id}, "
            f"chronotype={self.chronotype}, "
            f"tz={self.timezone}"
            f")>"
        )

    def to_local_time(self, dt: datetime) -> datetime:
        """Convert UTC datetime to user's local timezone."""
        import pytz

        tz = pytz.timezone(self.timezone)
        return dt.astimezone(tz)

    def get_preferred_hours_local(self) -> dict[str, time | None]:
        """Get preferred hours in user's local timezone."""
        return {
            "morning_start": self.preferred_morning_start,
            "morning_end": self.preferred_morning_end,
            "afternoon_start": self.preferred_afternoon_start,
            "afternoon_end": self.preferred_afternoon_end,
        }


class AvailabilityPattern(Base):  # type: ignore[misc]
    """Historical availability patterns for ML predictions.

    Aggregated data showing availability likelihood by day/hour.
    Updated periodically by analyzing historical calendar data.
    """

    __tablename__ = "availability_patterns"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "tenant_id",
            "day_of_week",
            "hour_block",
            name="uq_availability_pattern",
        ),
        CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="chk_day_of_week",
        ),
        CheckConstraint(
            "hour_block >= 0 AND hour_block <= 23",
            name="chk_hour_block",
        ),
        CheckConstraint(
            "availability_score >= 0.0 AND availability_score <= 1.0",
            name="chk_availability_score",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_confidence",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Time dimensions
    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # 0=Monday, 6=Sunday
    hour_block: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # 0-23 (1-hour blocks)

    # Statistics (last 90 days)
    total_slots: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    busy_slots: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    free_slots: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    tentative_slots: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Calculated metrics
    availability_score: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        nullable=False,
    )  # 0.0-1.0 likelihood of being free
    confidence: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )  # Based on sample size (0.0-1.0)

    # Additional metadata
    sample_weeks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    last_updated: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<AvailabilityPattern("
            f"user={self.user_id}, "
            f"day={self.day_of_week}, "
            f"hour={self.hour_block}, "
            f"score={self.availability_score:.2f}"
            f")>"
        )

    def calculate_availability_score(self) -> float:
        """Recalculate availability score from statistics."""
        if self.total_slots == 0:
            return 0.5

        # Weight: free = 1.0, tentative = 0.5, busy = 0.0
        weighted_score = (
            self.free_slots * 1.0 + self.tentative_slots * 0.5 + self.busy_slots * 0.0
        ) / self.total_slots

        return round(weighted_score, 2)

    def calculate_confidence(self) -> float:
        """Calculate confidence based on sample size."""
        # Confidence increases with more data
        # Max confidence at 12+ weeks of data
        if self.sample_weeks >= 12:
            return 1.0
        return round(self.sample_weeks / 12, 2)

    def update_from_stats(self) -> Self:
        """Update calculated fields from statistics."""
        self.availability_score = self.calculate_availability_score()
        self.confidence = self.calculate_confidence()
        return self


# ============================================================================
# PYDANTIC SCHEMAS
# ============================================================================


class TimeRange(BaseModel):
    """Time range for scheduling preferences."""

    model_config = ConfigDict(json_encoders={time: lambda v: v.isoformat()})

    start: time
    end: time

    @field_validator("end")
    @classmethod
    def end_after_start(
        cls,
        v: time,
        info: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> time:  # TODO(TYPE): replace Any with concrete type
        """Validate that end time is after start time."""
        if "start" in info.data and v <= info.data["start"]:
            raise ValueError("End time must be after start time")
        return v


class UserSchedulingProfileCreate(BaseModel):
    """Schema for creating user scheduling profile."""

    model_config = ConfigDict(use_enum_values=True)

    user_id: str = Field(..., min_length=1, max_length=255)
    chronotype: Chronotype = Chronotype.NEUTRAL
    timezone: str = Field(default="UTC", max_length=50)

    # Preferred time ranges
    preferred_morning_start: time | None = None
    preferred_morning_end: time | None = None
    preferred_afternoon_start: time | None = None
    preferred_afternoon_end: time | None = None

    # Focus time
    focus_time_min_duration: int = Field(default=120, ge=30, le=480)
    protect_focus_time: bool = True

    # Buffers (minutes)
    default_prep_buffer: int = Field(default=15, ge=0, le=120)
    default_recovery_buffer: int = Field(default=15, ge=0, le=120)
    travel_buffer_minutes: int = Field(default=30, ge=0, le=240)

    # Limits
    max_meetings_per_day: int = Field(default=6, ge=1, le=20)
    max_consecutive_meetings: int = Field(default=3, ge=1, le=10)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate timezone string."""
        try:
            import pytz

            if v not in pytz.all_timezones:
                raise ValueError(f"Invalid timezone: {v}")
        except ImportError:
            # pytz not installed, skip validation
            pass
        return v


class UserSchedulingProfileResponse(BaseModel):
    """Schema for user scheduling profile response."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    user_id: str
    chronotype: Chronotype
    timezone: str
    preferred_morning_start: time | None = None
    preferred_morning_end: time | None = None
    preferred_afternoon_start: time | None = None
    preferred_afternoon_end: time | None = None
    focus_time_min_duration: int
    protect_focus_time: bool
    default_prep_buffer: int
    default_recovery_buffer: int
    travel_buffer_minutes: int
    max_meetings_per_day: int
    max_consecutive_meetings: int
    last_pattern_analysis: datetime | None = None
    pattern_confidence: float
    created_at: datetime
    updated_at: datetime


class AvailabilityPrediction(BaseModel):
    """Single availability prediction slot."""

    start_time: datetime
    end_time: datetime
    availability_score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    pattern_type: str = Field(..., pattern=r"^(historical|default|declared_busy)$")


class AvailabilityPredictionResponse(BaseModel):
    """Response for availability prediction."""

    user_id: str
    start_date: datetime
    end_date: datetime
    predictions: list[AvailabilityPrediction]
    generated_at: datetime
    timezone: str = "UTC"


class ConflictInfo(BaseModel):
    """Information about a scheduling conflict."""

    participant_id: str
    participant_name: str | None = None
    participant_email: str | None = None
    conflicting_event_title: str
    conflicting_event_id: str | None = None
    conflict_start: datetime
    conflict_end: datetime
    conflict_type: str = Field(..., pattern=r"^(hard|soft|tentative)$")
    is_recurring: bool = False


class ResolutionOption(BaseModel):
    """Suggested resolution for a conflict."""

    type: str = Field(..., pattern=r"^(adjacent|alternative_day|shorter|virtual|async)$")
    description: str
    new_start: datetime | None = None
    new_end: datetime | None = None
    new_duration_minutes: int | None = Field(None, ge=5, le=480)
    confidence: float = Field(..., ge=0.0, le=1.0)
    impacted_participants: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)


class BufferConfig(BaseModel):
    """Suggested buffer configuration."""

    prep_buffer_minutes: int = Field(..., ge=0)
    recovery_buffer_minutes: int = Field(..., ge=0)
    travel_buffer_minutes: int = Field(..., ge=0)
    total_buffer_minutes: int = Field(..., ge=0)
    reasoning: str = ""


class QualityScoreBreakdown(BaseModel):
    """Detailed breakdown of meeting quality score."""

    focus_time_protection: int = Field(..., ge=0, le=25)
    energy_level: int = Field(..., ge=0, le=20)
    travel_efficiency: int = Field(..., ge=0, le=20)
    participant_availability: int = Field(..., ge=0, le=20)
    buffer_compliance: int = Field(..., ge=0, le=15)
    total_score: int = Field(..., ge=0, le=100)

    def get_grade(self) -> str:
        """Get letter grade based on total score."""
        if self.total_score >= 90:
            return "A"
        elif self.total_score >= 80:
            return "B"
        elif self.total_score >= 70:
            return "C"
        elif self.total_score >= 60:
            return "D"
        else:
            return "F"


class SmartScheduleOption(BaseModel):
    """A single smart scheduling option."""

    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"

    # Scores
    quality_score: int = Field(..., ge=0, le=100)
    quality_breakdown: QualityScoreBreakdown
    availability_score: int = Field(..., ge=0, le=100)
    focus_impact_score: int = Field(..., ge=0, le=100)
    energy_score: int = Field(..., ge=0, le=100)

    # Participants
    available_participants: list[str] = Field(default_factory=list)
    unavailable_participants: list[str] = Field(default_factory=list)
    tentative_participants: list[str] = Field(default_factory=list)

    # Conflicts and resolutions
    conflicts: list[ConflictInfo] = Field(default_factory=list)
    suggested_resolutions: list[ResolutionOption] = Field(default_factory=list)

    # Buffers
    suggested_buffers: BufferConfig

    # Metadata
    algorithm_version: str = "1.0"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SmartScheduleRequest(BaseModel):
    """Request for smart meeting scheduling."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    duration_minutes: int = Field(..., ge=15, le=480)

    # Participants
    required_participants: list[str] = Field(..., min_length=1, max_length=50)
    optional_participants: list[str] = Field(default_factory=list, max_length=50)
    min_required_attendance: int = Field(default=0, ge=0)  # 0 = all required

    # Time constraints
    earliest_start: datetime
    latest_end: datetime
    preferred_time_ranges: list[TimeRange] = Field(default_factory=list)
    excluded_dates: list[datetime] = Field(default_factory=list)

    # Quality preferences
    prefer_focus_time_protection: bool = True
    respect_chronotypes: bool = True
    avoid_early_morning: bool = True
    avoid_late_evening: bool = True
    prioritize_participant_preferences: bool = True

    # Room/location preferences
    preferred_room_type: str | None = None  # "conference", "huddle", "phone"
    require_video_conferencing: bool = False

    # Optimization
    max_suggestions: int = Field(default=5, ge=1, le=10)
    min_quality_score: int = Field(default=60, ge=0, le=100)
    optimization_strategy: str = Field(
        default="balanced", pattern=r"^(speed|quality|balanced|fairness)$"
    )

    @field_validator("latest_end")
    @classmethod
    def validate_time_range(
        cls,
        v: datetime,
        info: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> datetime:  # TODO(TYPE): replace Any with concrete type
        """Validate that latest_end is after earliest_start."""
        if "earliest_start" in info.data:
            earliest = info.data["earliest_start"]
            if v <= earliest:
                raise ValueError("latest_end must be after earliest_start")
            # Max 30 days range
            if (v - earliest).days > 30:
                raise ValueError("Date range cannot exceed 30 days")
        return v

    @field_validator("optional_participants")
    @classmethod
    def validate_unique_participants(
        cls,
        v: list[str],
        info: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]:  # TODO(TYPE): replace Any with concrete type
        """Ensure no overlap between required and optional participants."""
        if "required_participants" in info.data:
            required = set(info.data["required_participants"])
            optional = set(v)
            overlap = required & optional
            if overlap:
                raise ValueError(f"Participants cannot be both required and optional: {overlap}")
        return v


class SmartScheduleResponse(BaseModel):
    """Response for smart meeting scheduling."""

    request: SmartScheduleRequest
    options: list[SmartScheduleOption]
    total_options_considered: int
    total_options_filtered: int
    generated_at: datetime
    generation_time_ms: int
    algorithm_version: str = "1.0"

    def get_best_option(self) -> SmartScheduleOption | None:
        """Get the highest-scored option."""
        if not self.options:
            return None
        return max(self.options, key=lambda x: x.quality_score)

    def get_options_by_grade(self, grade: str) -> list[SmartScheduleOption]:
        """Get all options with a specific grade."""
        return [opt for opt in self.options if opt.quality_breakdown.get_grade() == grade.upper()]


class PatternAnalysisRequest(BaseModel):
    """Request to analyze user patterns."""

    user_id: str
    days_back: int = Field(default=90, ge=7, le=365)
    force_reanalysis: bool = False


class PatternAnalysisResponse(BaseModel):
    """Response from pattern analysis."""

    user_id: str
    events_analyzed: int
    date_range: str
    patterns_generated: int
    recommended_chronotype: Chronotype
    confidence: float
    analysis_time_ms: int
    completed_at: datetime


# ============================================================================
# CACHE/DTO CLASSES (For internal use)
# ============================================================================


class CachedUserProfile:
    """Cached user profile for performance."""

    def __init__(self, profile: UserSchedulingProfile, ttl_seconds: int = 300):
        self.profile = profile
        self.cached_at = datetime.now(timezone.utc)
        self.ttl_seconds = ttl_seconds

    def is_expired(self) -> bool:
        """Check if cache has expired."""
        age = (datetime.now(timezone.utc) - self.cached_at).total_seconds()
        return age > self.ttl_seconds


class TimeSlot:
    """Internal representation of a time slot."""

    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end = end
        self.duration = end - start

    def overlaps(self, other: "TimeSlot") -> bool:
        """Check if this slot overlaps with another."""
        return self.start < other.end and other.start < self.end

    def contains(self, dt: datetime) -> bool:
        """Check if datetime falls within this slot."""
        return self.start <= dt < self.end

    def __repr__(self) -> str:
        return f"<TimeSlot({self.start} to {self.end})>"
