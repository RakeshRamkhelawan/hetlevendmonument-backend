"""
Knowledge Models - Domain models for knowledge management system
Migrated from core.database.models (Phase 6 Task 6)

Usage:
    from src.core.knowledge.models import KnowledgeEntry
"""

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# Use SQLite-compatible JSON type for testing, PostgreSQL JSONB for production
JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB


class KnowledgeEntry(Base):  # type: ignore[misc]
    """
    KnowledgeEntry model voor FASE 3 kennisbeheer systeem
    Zoals gespecificeerd in STAP 3.1: velden voor id, content (Text), type (String), metadata (JSONB), en confidence_score (Float)
    Enhanced with TAAK 3.2 performance indexes

    MIGRATED from core.database.models (Phase 6 Task 6)
    SECURITY FIX (P5.1.4): Added tenant_id for RLS multi-tenant isolation
    """

    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # SECURITY FIX (P5.1.4): Added tenant_id for proper RLS isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-tenant isolation - FK to tenants.id",
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entry_metadata = mapped_column(
        JSONType, nullable=True
    )  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Performance-critical composite indexes
    __table_args__ = (
        # Index for tenant-scoped queries (most important for RLS)
        Index("idx_knowledge_tenant_type", "tenant_id", "type"),
        # Index for filtering by type and ordering by confidence score
        Index("idx_knowledge_type_confidence", "type", "confidence_score"),
        # Index for recent knowledge queries filtered by type
        Index("idx_knowledge_created_type", "created_at", "type"),
        # Composite index for complex search queries
        Index("idx_knowledge_search", "type", "created_at", "confidence_score"),
        # Index for high-confidence knowledge retrieval
        Index("idx_knowledge_confidence_created", "confidence_score", "created_at"),
        {"extend_existing": True},  # Allow redefinition if already exists
    )

    def __repr__(self) -> str:
        return f"<KnowledgeEntry(id={self.id}, type='{self.type}', confidence={self.confidence_score})>"
