"""
SQLAlchemy 2.0 ORM models for scheduling core capability.

All models use Mapped[] / mapped_column() style.
All queries MUST include tenant_id filtering.
"""

import uuid
from datetime import datetime, time, timezone
from typing import Any, Optional

from sqlalchemy import event as sa_event
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base
from src.core.database.mixins import SoftDeleteMixin, TimestampMixin
from src.core.scheduling.config import scheduling_config


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class CalendarEvent(Base, TimestampMixin, SoftDeleteMixin):  # type: ignore[misc]
    """A scheduled calendar event scoped to a tenant."""

    __tablename__ = "scheduling_calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    organizer_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    participants: Mapped[dict[str, Any] | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True, default=list
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, default="meeting")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduled")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    recurrence_rule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True, default=dict
    )

    __table_args__ = (
        Index(
            "idx_cal_event_tenant_organizer",
            "tenant_id",
            "organizer_id",
        ),
        Index(
            "idx_cal_event_tenant_user",
            "tenant_id",
            "user_id",
        ),
        Index(
            "idx_cal_event_tenant_time",
            "tenant_id",
            "start_time",
            "end_time",
        ),
    )

    @validates("start_time", "end_time")
    def _validate_time_range(self, key: str, value: datetime) -> datetime:
        if value is None:
            return value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        # Use configurable date ranges
        if not (scheduling_config.MIN_EVENT_DATE <= value <= scheduling_config.MAX_EVENT_DATE):
            raise ValueError(
                f"Date {value} is outside valid range "
                f"[{scheduling_config.MIN_EVENT_DATE.date()}-{scheduling_config.MAX_EVENT_DATE.date()}]"
            )
        return value

    @validates("priority")
    def _validate_priority(self, key: str, value: int) -> int:
        if not (1 <= value <= 9):
            raise ValueError("Priority must be between 1 and 9")
        return value


@sa_event.listens_for(CalendarEvent, "init")
def _calendar_event_set_user_id_default(target: Any, args: Any, kwargs: Any) -> None:  # TODO(TYPE): replace Any with concrete type
    """Default user_id to organizer_id when not explicitly provided."""
    if "user_id" not in kwargs and "organizer_id" in kwargs:
        kwargs["user_id"] = kwargs["organizer_id"]


class TimeBlock(Base, TimestampMixin, SoftDeleteMixin):  # type: ignore[misc]
    """Time block for focus-time protection and capacity planning."""

    __tablename__ = "scheduling_time_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    block_type: Mapped[str] = mapped_column(String(50), nullable=False, default="focus_time")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_hard_block: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_time_block_tenant_user", "tenant_id", "user_id"),
        Index(
            "idx_time_block_tenant_time",
            "tenant_id",
            "start_time",
            "end_time",
        ),
    )


class SchedulingConstraint(Base, TimestampMixin, SoftDeleteMixin):  # type: ignore[misc]
    """Hard and soft constraints for scheduling."""

    __tablename__ = "scheduling_constraints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    constraint_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_hard: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    parameters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)  # TODO(TYPE): replace Any with concrete type
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("idx_constraint_tenant_user", "tenant_id", "user_id"),)


class SchedulingPreference(Base, TimestampMixin, SoftDeleteMixin):  # type: ignore[misc]
    """User scheduling preferences -- one per user per tenant."""

    __tablename__ = "scheduling_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    timezone_name: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    working_hours_start: Mapped[time | None] = mapped_column(
        nullable=True, default=scheduling_config.DEFAULT_WORKING_HOURS_START
    )
    working_hours_end: Mapped[time | None] = mapped_column(
        nullable=True, default=scheduling_config.DEFAULT_WORKING_HOURS_END
    )
    preferred_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    buffer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    preferences_json: Mapped[dict[str, Any] | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True, default=dict
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            name="uq_scheduling_pref_tenant_user",
        ),
        Index("idx_pref_tenant_user", "tenant_id", "user_id"),
    )

    @validates("working_hours_start", "working_hours_end")
    def _coerce_time(self, key: str, value: object) -> time | None:
        if value is None or isinstance(value, time):
            return value
        if isinstance(value, str):
            return time.fromisoformat(value)
        raise TypeError(f"{key} must be a time or HH:MM string, got {type(value)}")
