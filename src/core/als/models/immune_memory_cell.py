"""Immune Memory Cell Model - Threat detection and learning."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class ImmuneMemoryCell(Base):  # type: ignore[misc]
    """Memory of past threats and how they were handled.

    This enables the immune system to learn from past attacks
    and respond faster to similar threats.
    """

    __tablename__ = "immune_memory_cells"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # [RED] CRITICAL: Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Threat identification
    threat_signature: Mapped[str] = mapped_column(String, nullable=False)  # Hash of threat pattern
    threat_type: Mapped[str] = mapped_column(String, nullable=False)  # rate_limit, anomaly, etc.
    threat_description: Mapped[str | None] = mapped_column(Text)

    # Response tracking
    antibodies_used: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, nullable=False
    )  # List of antibody IDs  # TODO(TYPE): replace Any with concrete type
    outcome: Mapped[Any | None] = mapped_column(
        JSONB
    )  # Result of response  # TODO(TYPE): replace Any with concrete type
    lessons_learned: Mapped[Any | None] = mapped_column(
        JSONB, default=list
    )  # TODO(TYPE): replace Any with concrete type

    # Learning metrics
    reinforced_count: Mapped[int | None] = mapped_column(Integer, default=1)  # How many times seen
    effectiveness_score: Mapped[float | None] = mapped_column(Float, default=0.0)  # 0.0 - 1.0

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_reinforced: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Indexes
    __table_args__ = (
        Index("idx_memory_tenant_signature", "tenant_id", "threat_signature", unique=True),
        Index("idx_memory_type", "threat_type"),
        Index("idx_memory_effectiveness", "effectiveness_score"),
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
