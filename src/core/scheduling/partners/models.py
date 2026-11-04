"""
SQLAlchemy models for Design Partner Program.

Tracks enterprise partners and their feedback during beta testing.
"""

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base
from src.core.database.mixins import TimestampMixin

if TYPE_CHECKING:
    pass


def _generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class DesignPartner(Base, TimestampMixin):  # type: ignore[misc]  # NOTE: Base has type Any due to SQLAlchemy declarative metaclass
    """
    Enterprise partner participating in the beta testing program.
    """

    __tablename__ = "scheduling_design_partners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)

    # Tenant relationship
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Partner details
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(50), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Program status
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="onboarding"
    )  # onboarding | active | completed | suspended

    # Testing period
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Configuration
    max_users: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    allowed_features: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Metrics tracking
    total_events_created: Mapped[int] = mapped_column(Integer, default=0)
    total_conflicts_detected: Mapped[int] = mapped_column(Integer, default=0)
    api_calls_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    feedback_entries: Mapped[list["PartnerFeedback"]] = relationship(
        "PartnerFeedback",
        back_populates="partner",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def is_active_program(self) -> bool:
        """Check if the partner program is currently active."""
        now = datetime.now(timezone.utc)
        return (
            self.status == "active"
            and self.start_date <= now <= self.end_date
            and self.deleted_at is None
        )

    def increment_metric(self, metric_name: str, amount: int = 1) -> None:
        """Increment a metric counter."""
        if metric_name == "events_created":
            self.total_events_created += amount
        elif metric_name == "conflicts_detected":
            self.total_conflicts_detected += amount
        elif metric_name == "api_calls":
            self.api_calls_count += amount
        elif metric_name == "errors":
            self.error_count += amount


class PartnerFeedback(Base, TimestampMixin):  # type: ignore[misc]  # NOTE: Base has type Any due to SQLAlchemy declarative metaclass
    """
    Feedback entry from a design partner.
    """

    __tablename__ = "scheduling_partner_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)

    # Partner relationship
    partner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scheduling_design_partners.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Reporter info
    reported_by: Mapped[str | None] = mapped_column(String(36), nullable=True)  # user_id
    reporter_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Classification
    feedback_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # bug | feature_request | usability | performance | other
    severity: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # critical | high | medium | low
    category: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # ui | api | integration | performance | security | documentation

    # Content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reproduction_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    environment: Mapped[dict[str, Any] | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # browser, OS, etc.
    attachments: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # file URLs

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open"
    )  # open | in_progress | resolved | closed
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 1-10

    # Assignment
    assigned_to: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # engineer user_id

    # Resolution
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    partner: Mapped["DesignPartner"] = relationship(
        "DesignPartner", back_populates="feedback_entries"
    )

    # Indexes
    __table_args__ = (
        Index("ix_feedback_status", "status"),
        Index("ix_feedback_severity", "severity"),
        Index("ix_feedback_created", "created_at"),
    )

    def assign(self, engineer_id: str) -> None:
        """Assign feedback to an engineer."""
        self.assigned_to = engineer_id
        self.status = "in_progress"

    def resolve(self, notes: str | None = None) -> None:
        """Mark feedback as resolved."""
        self.status = "resolved"
        self.resolution_notes = notes
        self.resolved_at = datetime.now(timezone.utc)

    def calculate_priority(self) -> int:
        """Calculate priority score based on severity and type."""
        severity_scores = {
            "critical": 10,
            "high": 7,
            "medium": 4,
            "low": 1,
        }
        type_scores = {
            "bug": 3,
            "performance": 3,
            "security": 5,
            "usability": 2,
            "feature_request": 1,
            "other": 1,
        }

        return severity_scores.get(self.severity, 0) + type_scores.get(self.feedback_type, 0)
