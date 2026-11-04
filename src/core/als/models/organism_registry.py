"""Organism Registry Model - Agent registration with tenant isolation."""

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class OrganismRegistry(Base):  # type: ignore[misc]
    """Agent registration in the symbiotic organism.

    Tracks agent health, workload, and emotional state per tenant.
    """

    __tablename__ = "organism_registry"

    id: Mapped[PyUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # [RED] CRITICAL: Tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_type: Mapped[str] = mapped_column(String, nullable=False)
    department: Mapped[str] = mapped_column(String, nullable=False)

    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_heartbeat: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Dynamic state
    workload: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=dict)
    emotional_state: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=dict)
    status: Mapped[str | None] = mapped_column(
        String, default="healthy"
    )  # healthy, stressed, zombie

    # Table constraints
    __table_args__ = (
        Index("idx_organism_tenant_agent", "tenant_id", "agent_id", unique=True),
        Index("idx_organism_heartbeat", "last_heartbeat"),
        Index("idx_organism_status", "tenant_id", "status"),
    )

    @validates("tenant_id")
    def validate_tenant_id(self, key: str, tenant_id: int) -> int:
        """Ensure tenant_id is valid."""
        if not tenant_id or tenant_id <= 0:
            raise ValueError(f"Invalid tenant_id: {tenant_id}")
        return tenant_id

    @validates("status")
    def validate_status(self, key: str, status: str) -> str:
        """Ensure valid status values."""
        valid = ["healthy", "stressed", "overloaded", "zombie", "recovering"]
        if status not in valid:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid}")
        return status
