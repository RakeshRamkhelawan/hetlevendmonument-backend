"""
ORM models for LearningLoop persistence.

Tables: learning_patterns, adaptation_rules, learning_insights
Refactored for specific use with FeedbackLoopProcessor.
"""

import os
from typing import Any, Optional

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

# Use JSONB for PostgreSQL, fallback for SQLite in tests
JSONType = JSON if os.getenv("TESTING") == "1" else JSONB
StringListType = ARRAY(String).with_variant(JSON, "sqlite")


class LearningPatternModel(Base):  # type: ignore[misc]
    """Persisted learning pattern discovered by the LearningLoop."""

    __tablename__ = "learning_patterns"
    __table_args__ = (
        Index("ix_learning_patterns_tenant", "tenant_id"),
        Index("ix_learning_patterns_type", "pattern_type", "is_active"),
        Index("ix_learning_patterns_agent", "tenant_id", "agent_id"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(
        String(128),  # Changed from Integer to match tenant_id format
        nullable=False,
        index=True,
    )
    pattern_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    pattern_type: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger_conditions: Mapped[Any] = mapped_column(JSONType, nullable=False)  # TODO(TYPE): replace Any with concrete type
    learned_behavior: Mapped[Any] = mapped_column(JSONType, nullable=False)  # TODO(TYPE): replace Any with concrete type
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<LearningPattern(id={self.pattern_id}, "
            f"type={self.pattern_type}, active={self.is_active})>"
        )


class AdaptationRuleModel(Base):  # type: ignore[misc]
    """
    Persisted adaptation rule derived from learning patterns.

    Refactored for specific use with FeedbackLoopProcessor:
    - Direct columns for trigger_keywords, target_supervisor
    - Better indexing for routing lookups
    - String tenant_id for consistency
    """

    __tablename__ = "adaptation_rules"
    __table_args__ = (
        Index("ix_adaptation_rules_tenant", "tenant_id"),
        Index("ix_adaptation_rules_active", "is_active", "priority"),
        # Composite index for fast routing lookups
        Index("ix_adaptation_rules_tenant_active", "tenant_id", "is_active"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(
        String(128), primary_key=True
    )  # UUID string from Pydantic model
    rule_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    tenant_id = mapped_column(
        String(128),  # Changed from Integer to match tenant_id format
        nullable=False,
        index=True,
    )
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False, default="routing_correction")
    source_pattern_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Specific columns for our use case (instead of generic JSON condition/action)
    trigger_keywords: Mapped[Any | None] = mapped_column(StringListType, default=list)  # TODO(TYPE): replace Any with concrete type
    trigger_patterns: Mapped[Any | None] = mapped_column(StringListType, default=list)  # TODO(TYPE): replace Any with concrete type
    target_supervisor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Rule metadata
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Usage metrics
    application_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    times_applied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # State
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Legacy fields for backward compatibility (stored as JSON)
    condition: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    action: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    parameters: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<AdaptationRule(id={self.id}, "
            f"type={self.rule_type}, active={self.is_active}, "
            f"priority={self.priority})>"
        )


class LearningInsightModel(Base):  # type: ignore[misc]
    """
    Persisted insight generated by the LearningLoop.
    Refactored for specific use with FeedbackLoopProcessor.
    """

    __tablename__ = "learning_insights"
    __table_args__ = (
        Index("ix_learning_insights_tenant", "tenant_id"),
        Index("ix_learning_insights_type", "insight_type", "is_actionable"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)  # UUID string
    insight_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    tenant_id = mapped_column(
        String(128),  # Changed from Integer
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="system", index=True
    )
    insight_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Feedback data
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 scale
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    impact_assessment: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    recommended_actions: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type

    # Context
    context: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    evidence: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type

    # State
    processed: Mapped[bool | None] = mapped_column(Boolean, default=False)
    adaptation_applied: Mapped[bool | None] = mapped_column(Boolean, default=False)
    is_actionable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<LearningInsight(id={self.id}, type={self.insight_type}, conversation={self.conversation_id})>"


__all__ = [
    "LearningPatternModel",
    "AdaptationRuleModel",
    "LearningInsightModel",
]
