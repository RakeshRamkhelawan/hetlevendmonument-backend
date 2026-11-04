"""
ORM models for StrategyEngine persistence.

Tables: strategic_objectives, strategic_insights, strategies
"""

import os
from typing import Any, Optional

from sqlalchemy import JSON as SQLiteJSON
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base

JSONType = SQLiteJSON if os.getenv("TESTING") == "1" else JSONB


class StrategicObjectiveModel(Base):  # type: ignore[misc]
    """Persisted strategic objective managed by the StrategyEngine."""

    __tablename__ = "strategic_objectives"
    __table_args__ = (
        Index("ix_strategic_obj_tenant", "tenant_id"),
        Index("ix_strategic_obj_status", "tenant_id", "status"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    objective_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    success_criteria: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    key_results: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategicObjective(id={self.objective_id}, "
            f"status={self.status}, progress={self.progress})>"
        )


class StrategicInsightModel(Base):  # type: ignore[misc]
    """Persisted strategic insight from the StrategyEngine."""

    __tablename__ = "strategic_insights"
    __table_args__ = (
        Index("ix_strategic_insights_tenant", "tenant_id"),
        Index("ix_strategic_insights_type", "strategy_type"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    insight_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    strategy_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    impact_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    urgency_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    supporting_evidence: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    recommended_actions: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    risks: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    opportunities: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<StrategicInsight(id={self.insight_id}, "
            f"type={self.strategy_type}, impact={self.impact_score})>"
        )


class StrategyModel(Base):  # type: ignore[misc]
    """Persisted strategy developed by the StrategyEngine."""

    __tablename__ = "strategies"
    __table_args__ = (
        Index("ix_strategies_tenant", "tenant_id"),
        Index("ix_strategies_type", "tenant_id", "strategy_type", "status"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    strategy_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    analysis: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    recommendations: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    implementation_plan: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    success_metrics: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    context_data: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # TODO(TYPE): replace Any with concrete type

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<Strategy(id={self.strategy_id}, "
            f"type={self.strategy_type}, status={self.status})>"
        )


__all__ = [
    "StrategicObjectiveModel",
    "StrategicInsightModel",
    "StrategyModel",
]
