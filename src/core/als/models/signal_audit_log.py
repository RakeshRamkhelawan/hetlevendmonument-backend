"""Signal Audit Log Model - Security audit trail for all signals."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class SignalAuditLog(Base):  # type: ignore[misc]
    """Audit log for all signals in the nervous system.

    CRITICAL SECURITY:
    - All signals are logged with SHA-256 hash for integrity
    - Tenant isolation enforced via RLS
    - Processing latency tracked for performance monitoring
    """

    __tablename__ = "signal_audit_log"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # [RED] CRITICAL: Tenant isolation
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    signal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    source_agent: Mapped[str] = mapped_column(String, nullable=False)
    target_agents: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB
    )  # List of agent IDs  # TODO(TYPE): replace Any with concrete type

    # Signal classification
    tier: Mapped[str] = mapped_column(
        String, nullable=False
    )  # REFLEX, COGNITIVE, EMOTIONAL, SYNAPTIC

    # [RED] SECURITY: SHA-256 hash of payload for integrity verification
    payload_hash: Mapped[str | None] = mapped_column(String(64))
    payload_size_bytes: Mapped[int | None] = mapped_column(Integer)

    # Timing
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    processing_latency_ms: Mapped[int | None] = mapped_column(Integer)

    # Immune system
    antibody_triggered: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # Which antibody fired

    # Indexes
    __table_args__ = (
        Index("idx_signal_audit_tenant_time", "tenant_id", "processed_at"),
        Index("idx_signal_audit_agent", "source_agent"),
        Index("idx_signal_audit_tier", "tier"),
    )

    @validates("tenant_id")
    def validate_tenant_id(
        self,
        key: str,
        tenant_id: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        if not tenant_id or tenant_id <= 0:
            raise ValueError(f"Invalid tenant_id: {tenant_id}")
        return tenant_id

    @validates("tier")
    def validate_tier(
        self,
        key: str,
        tier: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        valid = ["REFLEX", "COGNITIVE", "EMOTIONAL", "SYNAPTIC", "BROADCAST"]
        if tier not in valid:
            raise ValueError(f"Invalid tier: {tier}")
        return tier
