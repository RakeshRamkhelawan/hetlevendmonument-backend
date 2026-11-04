"""
SQLAlchemy 2.0 ORM model for external calendar integrations.

Stores OAuth tokens (Fernet-encrypted at rest) for Google Calendar
and Microsoft Outlook calendar providers.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base
from src.core.database.mixins import SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from src.core.scheduling.webhooks.models import SyncConflict, WebhookRegistration


def _generate_uuid() -> str:
    return str(uuid.uuid4())


class CalendarIntegration(Base, TimestampMixin, SoftDeleteMixin):  # type: ignore[misc]
    """External calendar OAuth token storage.

    SECURITY: access_token_encrypted and refresh_token_encrypted are
    Fernet-encrypted.  Decryption happens only in the service layer via
    ``TokenEncryptionService``.

    One row per (tenant, user, provider) -- enforced by UniqueConstraint.
    """

    __tablename__ = "scheduling_calendar_integrations"
    __allow_unmapped__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_generate_uuid)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Provider identification
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # "google" | "outlook"
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_calendar_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="primary"
    )

    # OAuth tokens -- encrypted at rest
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    token_scope: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Sync state
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_token: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )  # Google: syncToken, Outlook: deltaToken

    # Relationships (Phase 4A: OAuth Complete Flow)
    webhook_registrations: Mapped[list["WebhookRegistration"]] = relationship(
        "WebhookRegistration",
        back_populates="integration",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    sync_conflicts: Mapped[list["SyncConflict"]] = relationship(
        "SyncConflict",
        back_populates="integration",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "provider",
            name="uq_calendar_integration_user_provider",
        ),
        Index("idx_cal_integ_tenant_user", "tenant_id", "user_id"),
        Index("idx_cal_integ_provider", "tenant_id", "provider"),
    )


# Import webhooks models AFTER CalendarIntegration is defined
# This ensures SQLAlchemy can resolve the string references in relationships
try:
    from src.core.scheduling.webhooks.models import SyncConflict, WebhookRegistration
except ImportError:
    pass  # Models may not be available during initial import
