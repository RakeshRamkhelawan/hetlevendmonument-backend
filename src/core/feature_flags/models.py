"""
FeatureFlag Model - Domain model for per-tenant feature flags

Migrated from core.database.models in Phase 7.
This is the authoritative model for feature flag data.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# Use SQLite-compatible JSON type for testing, PostgreSQL JSONB for production
JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB


class FeatureFlag(Base):  # type: ignore[misc]  # NOTE: Base has type Any due to SQLAlchemy declarative metaclass
    """
    Per-tenant feature flag state for monetization

    Enables subscription tier gating:
    - Starter: core_agents, basic_analytics, api_access
    - Pro: Starter + memory_mcp, advanced_analytics, custom_branding, etc.
    - Enterprise: All features including SSO, custom_agents, audit_logs, etc.
    """

    __tablename__ = "feature_flags"
    __table_args__ = (
        Index("ix_feature_tenant_name", "tenant_id", "feature_name", unique=True),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    # Tenant ownership - Integer to match tenants.id type
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Feature configuration
    feature_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Metadata
    config: Mapped[Any | None] = mapped_column(JSONType, default=dict)  # Feature-specific config  # TODO(TYPE): replace Any with concrete type

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )
