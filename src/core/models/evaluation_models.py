"""
Evaluation Models - Database schema for RAG evaluation results
Stores metrics for correctness, faithfulness, relevance, etc.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base


class EvaluationRunModel(Base):  # type: ignore[misc]
    """
    Evaluation Run model for batch evaluations
    Tracks status of multi-sample evaluation runs
    """

    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Run Configuration
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    num_samples: Mapped[int | None] = mapped_column(Integer, default=0)

    # Status tracking
    status = mapped_column(String(50), default="pending")  # pending, running, completed, failed

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Aggregated Metrics (for completed runs)
    avg_faithfulness: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_context_precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_answer_relevancy: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_context_recall: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Error tracking
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    metadata_ = mapped_column("metadata", JSON, default=dict)

    # Relationships
    tenant = relationship("Tenant")
    results = relationship("EvaluationResult", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_eval_run_tenant_status", "tenant_id", "status"),
        Index("idx_eval_run_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<EvaluationRun(id={self.id}, tenant_id={self.tenant_id}, status={self.status})>"


class EvaluationResult(Base):  # type: ignore[misc]
    """
    RAG Evaluation Result model
    Stores detailed metrics for a single RAG triplet (Query, Context, Response)
    """

    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Link to batch run (optional - can be standalone)
    run_id = mapped_column(
        Integer,
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Multi-tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # RAG Triplet
    query: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    contexts: Mapped[Any] = mapped_column(JSON, nullable=False)  # List of strings  # TODO(TYPE): replace Any with concrete type
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Primary Metrics
    faithfulness: Mapped[float | None] = mapped_column(Float, default=0.0)
    relevance: Mapped[float | None] = mapped_column(Float, default=0.0)
    correctness: Mapped[float | None] = mapped_column(Float, default=0.0)
    precision: Mapped[float | None] = mapped_column(Float, default=0.0)
    recall: Mapped[float | None] = mapped_column(Float, default=0.0)

    # Retrieval Metrics
    context_precision: Mapped[float | None] = mapped_column(Float, default=0.0)
    context_recall: Mapped[float | None] = mapped_column(Float, default=0.0)

    # Metadata
    latency_ms: Mapped[float | None] = mapped_column(Float, default=0.0)
    engine_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_ = mapped_column("metadata", JSON, default=dict)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    tenant = relationship("Tenant")
    run = relationship("EvaluationRunModel", back_populates="results")

    # Indexes
    __table_args__ = (
        Index("idx_eval_tenant_created", "tenant_id", "created_at"),
        Index("idx_eval_faithfulness", "faithfulness"),
        Index("idx_eval_run_id", "run_id"),
    )

    def __repr__(self) -> str:
        return f"<EvaluationResult(id={self.id}, tenant_id={self.tenant_id}, faithfulness={self.faithfulness:.2f})>"
