"""
Database models for autonomous workflow.

SECURITY FIX (P5.1.4):
- Changed from local declarative_base to shared Base from src.core.database.database
- Added tenant_id for proper RLS multi-tenant isolation
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class WorkflowExperience(Base):  # type: ignore[misc]
    """Model for storing workflow experiences and feedback.

    SECURITY FIX (P5.1.4): Added tenant_id for RLS isolation
    """

    __tablename__ = "workflow_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # SECURITY FIX (P5.1.4): Added tenant_id for proper RLS isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-tenant isolation - FK to tenants.id",
    )
    workflow_type: Mapped[str] = mapped_column(String, nullable=False)
    input_data: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=False
    )  # TODO(TYPE): replace Any with concrete type
    output_data: Mapped[Any] = mapped_column(
        JSON, nullable=False
    )  # TODO(TYPE): replace Any with concrete type
    feedback_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_processed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Performance indexes for tenant-scoped queries
    __table_args__ = (
        Index("idx_workflow_exp_tenant", "tenant_id", "workflow_type"),
        Index("idx_workflow_exp_processed", "is_processed", "created_at"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return f"<WorkflowExperience(id={self.id}, type={self.workflow_type}, tenant_id={self.tenant_id})>"
