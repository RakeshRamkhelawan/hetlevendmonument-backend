"""
Learning Models - Domain models for adaptive learning system
Migrated from core.database.models (Phase 6 Task 6)

Usage:
    from src.core.learning.models import LearningExperience
"""

import os
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# Use SQLite-compatible JSON type for testing, PostgreSQL JSONB for production
JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB


class LearningExperience(Base):  # type: ignore[misc]
    """
    LearningExperience model voor FASE 6 adaptive learning engine persistentie
    Zoals gespecificeerd in STAP 6.1.3: persistentie voor learning events
    Enhanced with TAAK 3.2 performance indexes for adaptive learning queries

    MIGRATED from core.database.models (Phase 6 Task 6)
    SECURITY FIX (P5.1.4): Added tenant_id for RLS multi-tenant isolation
    """

    __tablename__ = "learning_experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # SECURITY FIX (P5.1.4): Added tenant_id for proper RLS isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-tenant isolation - FK to tenants.id",
    )
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    task_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    context: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    metrics: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Performance indexes for adaptive learning queries
    __table_args__ = (
        # Index for tenant-scoped agent performance analysis (most common query)
        Index("idx_learning_tenant_agent", "tenant_id", "agent_id"),
        # Index for agent performance analysis (most common query)
        Index("idx_learning_agent_task", "agent_id", "task_type"),
        # Index for success rate analysis over time
        Index("idx_learning_success_time", "success", "created_at"),
        # Composite index for comprehensive performance queries
        Index("idx_learning_performance", "agent_id", "task_type", "success", "created_at"),
        # Index for recent learning experiences
        Index("idx_learning_recent", "created_at", "agent_id"),
        # Index for event type analysis
        Index("idx_learning_event_time", "event_type", "created_at"),
        {"extend_existing": True},  # Allow redefinition if already exists
    )

    def __repr__(self) -> str:
        return f"<LearningExperience(id={self.id}, event_id='{self.event_id}', success={self.success})>"
