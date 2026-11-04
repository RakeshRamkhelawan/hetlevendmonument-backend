"""Agent Synapse Model - Tracks agent-to-agent connections."""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from src.core.database.database import Base


class AgentSynapse(Base):  # type: ignore[misc]
    """Tracks communication patterns between agents.

    Stronger connections indicate agents that frequently collaborate.
    This helps the orchestrator optimize task delegation.
    """

    __tablename__ = "agent_synapses"

    # [RED] CRITICAL: Tenant isolation (part of composite PK)
    tenant_id = mapped_column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    agent_a: Mapped[str] = mapped_column(String, nullable=False)
    agent_b: Mapped[str] = mapped_column(String, nullable=False)

    # Connection metrics
    connection_strength: Mapped[float | None] = mapped_column(Float, default=0.0)  # 0.0 - 1.0
    last_communication: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    communication_count: Mapped[int | None] = mapped_column(Integer, default=0)

    # Metadata
    successful_collaborations: Mapped[int | None] = mapped_column(Integer, default=0)
    failed_collaborations: Mapped[int | None] = mapped_column(Integer, default=0)

    # Composite primary key
    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "agent_a", "agent_b"),
        Index("idx_synapses_strength", "tenant_id", "connection_strength"),
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

    @validates("connection_strength")
    def validate_strength(
        self,
        key: str,
        value: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Connection strength must be between 0.0 and 1.0, got {value}")
        return value

    def record_communication(self, successful: bool = True) -> None:
        """Record a communication event."""
        self.last_communication = datetime.now(timezone.utc)
        self.communication_count = (self.communication_count or 0) + 1

        if successful:
            self.successful_collaborations = (self.successful_collaborations or 0) + 1
        else:
            self.failed_collaborations = (self.failed_collaborations or 0) + 1

        # Update connection strength based on success rate
        total = (self.successful_collaborations or 0) + (self.failed_collaborations or 0)
        if total > 0:
            self.connection_strength = (self.successful_collaborations or 0) / total
