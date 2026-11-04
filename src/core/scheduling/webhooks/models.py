"""
SQLAlchemy models for webhook registrations and sync conflicts.

These models support the OAuth Complete Flow feature for real-time
calendar synchronization via webhooks from Google and Outlook.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base
from src.core.database.mixins import TimestampMixin

if TYPE_CHECKING:
    from src.core.scheduling.integrations.models import CalendarIntegration


def _generate_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class WebhookRegistration(Base, TimestampMixin):  # type: ignore[misc]
    """
    Stores webhook channel/subscription registrations for calendar integrations.

    Supports both Google Calendar (channel-based) and Outlook (subscription-based)
    webhook mechanisms with proper security validation fields.

    SECURITY: tenant_id added for multi-tenant isolation (Fase 0.2)
    """

    __tablename__ = "scheduling_webhook_registrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)

    # Multi-tenant isolation (Fase 0.2 security fix)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Foreign key to calendar integration
    integration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scheduling_calendar_integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Provider type
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Values: "google" | "outlook"

    # Google-specific fields
    channel_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Outlook-specific fields
    subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_state: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Secret for validation

    # Common fields
    expiration_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    integration: Mapped["CalendarIntegration"] = relationship(
        "CalendarIntegration", back_populates="webhook_registrations"
    )

    # Indexes
    __table_args__ = (
        Index("ix_webhook_channel_id", "channel_id"),
        Index("ix_webhook_subscription_id", "subscription_id"),
        Index("ix_webhook_expiration", "expiration_date"),
    )

    def is_expired(self) -> bool:
        """Check if the webhook registration has expired."""
        return datetime.now(tz=self.expiration_date.tzinfo) >= self.expiration_date

    def needs_refresh(self, hours_before: int = 24) -> bool:
        """Check if webhook needs refresh (within hours_before of expiration)."""
        from datetime import timedelta

        threshold = datetime.now(tz=self.expiration_date.tzinfo) + timedelta(hours=hours_before)
        return threshold >= self.expiration_date


class SyncConflict(Base, TimestampMixin):  # type: ignore[misc]
    """
    Tracks conflicts detected during calendar synchronization.

    Conflicts occur when both local and external versions of an event
    have been modified independently (or external event is deleted).

    SECURITY: tenant_id added for multi-tenant isolation (Fase 0.2)
    """

    __tablename__ = "scheduling_sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)

    # Multi-tenant isolation (Fase 0.2 security fix)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    # Foreign key to integration
    integration_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("scheduling_calendar_integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event references
    local_event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Conflict details
    conflict_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # time_overlap | title_mismatch | deleted_externally | updated_both
    severity: Mapped[str] = mapped_column(
        String(10), default="medium", nullable=False
    )  # high | medium | low

    # Snapshots for comparison
    local_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)  # TODO(TYPE): replace Any with concrete type
    external_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)  # TODO(TYPE): replace Any with concrete type

    # Resolution tracking
    resolution_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending | auto_resolved | manual_resolved | ignored
    resolution_strategy: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # keep_local | keep_external | merge | create_duplicate
    resolved_by: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # user_id who resolved
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    integration: Mapped["CalendarIntegration"] = relationship(
        "CalendarIntegration", back_populates="sync_conflicts"
    )

    # Indexes
    __table_args__ = (
        Index("ix_conflicts_status", "resolution_status"),
        Index("ix_conflicts_integration", "integration_id", "resolution_status"),
    )

    def mark_resolved(self, strategy: str, resolved_by: str) -> None:
        """Mark conflict as resolved."""
        self.resolution_status = "manual_resolved"
        self.resolution_strategy = strategy
        self.resolved_by = resolved_by
        self.resolved_at = datetime.now(tz=self.created_at.tzinfo)

    def mark_auto_resolved(self, strategy: str) -> None:
        """Mark conflict as auto-resolved by system."""
        self.resolution_status = "auto_resolved"
        self.resolution_strategy = strategy
        self.resolved_at = datetime.now(tz=self.created_at.tzinfo)
