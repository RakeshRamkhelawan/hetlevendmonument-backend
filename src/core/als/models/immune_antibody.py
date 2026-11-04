"""Immune Antibody Model - Automated threat response actions."""

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class ImmuneAntibody(Base):  # type: ignore[misc]
    """Automated response to specific threat patterns.

    Antibodies are like automated firewall rules that trigger
    when specific threat patterns are detected.
    """

    __tablename__ = "immune_antibodies"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # [RED] CRITICAL: Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)

    # What to detect
    target_antigen: Mapped[str] = mapped_column(String, nullable=False)  # Pattern to match

    # What to do
    action_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # block, rate_limit, isolate, alert
    action_config: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, default=dict
    )  # Action parameters

    # Effectiveness tracking
    effectiveness: Mapped[float | None] = mapped_column(Float, default=0.5)  # 0.0 - 1.0
    trigger_count: Mapped[int | None] = mapped_column(Integer, default=0)
    false_positive_count: Mapped[int | None] = mapped_column(Integer, default=0)

    # Side effects (what else happens when this triggers)
    side_effects: Mapped[list[object] | None] = mapped_column(JSONB, default=list)

    # Origin
    created_from: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("immune_memory_cells.id"), nullable=True
    )

    is_auto_generated: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # Created by immune system?
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Indexes
    __table_args__ = (
        Index("idx_antibodies_tenant_name", "tenant_id", "name", unique=True),
        Index("idx_antibodies_target", "target_antigen"),
        Index("idx_antibodies_action", "action_type"),
        Index("idx_antibodies_active", "is_active"),
    )

    @validates("tenant_id")
    def validate_tenant_id(self, key: str, tenant_id: int) -> int:
        if not tenant_id or tenant_id <= 0:
            raise ValueError(f"Invalid tenant_id: {tenant_id}")
        return tenant_id

    @validates("effectiveness")
    def validate_effectiveness(self, key: str, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Effectiveness must be between 0.0 and 1.0, got {value}")
        return value

    @validates("action_type")
    def validate_action_type(self, key: str, action_type: str) -> str:
        valid = [
            "block",
            "rate_limit",
            "quarantine",
            "isolate_tenant",
            "alert",
            "circuit_break",
        ]
        if action_type not in valid:
            raise ValueError(f"Invalid action_type: {action_type}. Must be one of {valid}")
        return action_type
