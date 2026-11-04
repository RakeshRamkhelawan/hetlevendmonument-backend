"""Database models for inbound notification processing."""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class ChannelType(str, Enum):
    """Supported inbound channels."""

    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class MessageStatus(str, Enum):
    """Processing status for inbound messages."""

    UNPROCESSED = "unprocessed"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class IntentType(str, Enum):
    """Detected intent types."""

    REPLY = "reply"
    COMMAND = "command"
    APPROVE = "approve"
    REJECT = "reject"
    BOUNCE = "bounce"
    OUT_OF_OFFICE = "out_of_office"
    UNSUBSCRIBE = "unsubscribe"
    HELP = "help"
    QUERY_STATUS = "query_status"
    UNKNOWN = "unknown"


class InboundMessage(Base):  # type: ignore[misc]
    """Unified inbound message storage for all channels.

    Stores emails, SMS, WhatsApp messages in a single table
    for unified processing and audit trail.
    """

    __tablename__ = "inbound_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Channel information
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(50))  # twilio, messagebird, gmail, etc.

    # Sender information
    from_address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    from_name: Mapped[str | None] = mapped_column(String(255))

    # Recipient information
    to_address: Mapped[str | None] = mapped_column(String(255))  # For SMS/single recipient
    to_addresses: Mapped[list[str] | None] = mapped_column(JSONB)  # For email multiple recipients

    # Content
    subject: Mapped[str | None] = mapped_column(String(500))
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)

    # Threading (for email replies)
    message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(255))

    # Media (for SMS/WhatsApp)
    media_urls: Mapped[list[str] | None] = mapped_column(JSONB)

    # Processing
    status: Mapped[str] = mapped_column(String(50), default=MessageStatus.UNPROCESSED, index=True)
    intent: Mapped[str | None] = mapped_column(String(50))
    intent_confidence: Mapped[float | None] = mapped_column(Float)
    entities: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    # Routing
    routed_to: Mapped[str | None] = mapped_column(String(50))  # ticket_id, agent_id, workflow_id
    routing_decision: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Raw data for debugging
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    def __repr__(self) -> str:
        return (
            f"<InboundMessage(id={self.id}, channel={self.channel}, "
            f"from={self.from_address}, status={self.status})>"
        )


class ContactOptOut(Base):  # type: ignore[misc]
    """GDPR-compliant opt-out tracking.

    Tracks when users unsubscribe from communications.
    Respected across all channels.
    """

    __tablename__ = "contact_opt_outs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ADR-005: NOT NULL -- opt-outs are tracked per-tenant, respected across that
    # tenant's channels (email/sms/whatsapp), not globally across tenants.
    # SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D).
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Contact information
    contact: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    contact_type: Mapped[str] = mapped_column(String(20), nullable=False)  # email, phone

    # Opt-out details
    opted_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    source: Mapped[str | None] = mapped_column(String(50))  # user_request, bounce, complaint, admin
    channel: Mapped[str] = mapped_column(String(50), default="all")  # email, sms, whatsapp, all

    # Compliance tracking
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)

    # Reference to original message
    inbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inbound_messages.id", ondelete="SET NULL")
    )

    # De migratie maakt deze constraint AL (ADR-036 OP-160).
    #
    # `b2c3d4e5f6a7_add_notifications_inbound_tables_tenant_hardening.py:107-108` zet
    # `CONSTRAINT uq_contact_opt_outs_tenant_contact_channel UNIQUE (tenant_id, contact,
    # channel)`. Het model kende hem niet, en dat verschil is niet cosmetisch: de
    # testomgeving bouwt het schema met `create_all()` uit de MODELLEN, niet uit de
    # migraties. Een dubbele opt-out werd daar dus geaccepteerd terwijl productie hem
    # weigert -- de ene omgeving bewijst dan niets over de andere, en juist bij een
    # opt-out is een duplicaat een AVG-relevante fout (welke rij telt?).
    #
    # De naam is exact die van de migratie, zodat `alembic check` beide kanten als
    # dezelfde constraint ziet in plaats van een verschil te melden.
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "contact", "channel", name="uq_contact_opt_outs_tenant_contact_channel"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ContactOptOut(contact={self.contact}, type={self.contact_type}, "
            f"channel={self.channel})>"
        )


class EmailBounce(Base):  # type: ignore[misc]
    """Track email bounces for deliverability monitoring.

    Helps maintain sender reputation by tracking
    and acting on bounce notifications.
    """

    __tablename__ = "email_bounces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ADR-005: NOT NULL -- bounces are attributed to the tenant whose outbound
    # message triggered them. SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D).
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Bounce identification
    original_message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    bounce_message_id: Mapped[str | None] = mapped_column(String(255))

    # Bounce details
    bounce_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # hard, soft, complaint, unsubscribe
    bounce_reason: Mapped[str | None] = mapped_column(Text)
    bounce_code: Mapped[str | None] = mapped_column(String(50))

    # Affected address
    bounced_address: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bounced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Action taken
    marked_invalid: Mapped[bool] = mapped_column(Boolean, default=False)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Raw bounce data
    raw_bounce_content: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return (
            f"<EmailBounce(address={self.bounced_address}, type={self.bounce_type}, "
            f"marked_invalid={self.marked_invalid})>"
        )
