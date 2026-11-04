"""
Experiment Models for A/B Testing

Database models for managing A/B testing experiments at company level.
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON as JSONType
from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base


class Experiment(Base):  # type: ignore[misc]
    """A/B testing experiment definition."""

    __tablename__ = "experiments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Experiment timeline
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Experiment status: draft, running, paused, completed
    status: Mapped[str] = mapped_column(String(20), server_default="draft", nullable=False)

    # Traffic split for control vs treatment (0.5 = 50/50)
    traffic_split: Mapped[float] = mapped_column(Float, server_default="0.5", nullable=False)

    # Tenant isolation (TI-003 / AUDIT-2026-06-26). ADR-005: NOT NULL -- A/B-testing
    # experiments are inherently tenant-scoped (no platform-wide-experiment use case
    # exists in this codebase). SP-DATA-ARCH-1 (AUDIT-ARCH-2026-07-02 Dag 3 Groep D).
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Creator reference
    created_by: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    variants = relationship(
        "ExperimentVariant",
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
    assignments = relationship(
        "ExperimentAssignment",
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
    events = relationship(
        "ExperimentEvent",
        back_populates="experiment",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_experiments_status", "status"),
        Index("ix_experiments_created_by", "created_by"),
        Index("ix_experiments_start_date", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<Experiment(id={self.id}, name={self.name}, status={self.status})>"


class ExperimentVariant(Base):  # type: ignore[misc]
    """Variant configuration for an experiment (control or treatment)."""

    __tablename__ = "experiment_variants"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    experiment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Variant name: "control" or "treatment"
    name: Mapped[str] = mapped_column(String(50), nullable=False)

    # Variant-specific configuration stored as JSON
    config: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONType, nullable=True
    )  # TODO(TYPE): replace Any with concrete type

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    experiment = relationship("Experiment", back_populates="variants")

    __table_args__ = (
        Index("ix_experiment_variants_experiment_id", "experiment_id"),
        Index("ix_experiment_variants_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<ExperimentVariant(experiment={self.experiment_id}, name={self.name})>"


class ExperimentAssignment(Base):  # type: ignore[misc]
    """Tracks which company is assigned to which variant in an experiment."""

    __tablename__ = "experiment_assignments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    experiment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Company assigned to this variant
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # Assigned variant: "control" or "treatment"
    variant: Mapped[str] = mapped_column(String(50), nullable=False)

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    experiment = relationship("Experiment", back_populates="assignments")

    __table_args__ = (
        Index("ix_experiment_assignments_experiment_id", "experiment_id"),
        Index("ix_experiment_assignments_company_id", "company_id"),
        Index(
            "ix_experiment_assignments_experiment_company",
            "experiment_id",
            "company_id",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExperimentAssignment(experiment={self.experiment_id}, "
            f"company={self.company_id}, variant={self.variant})>"
        )


class ExperimentEvent(Base):  # type: ignore[misc]
    """Events tracked during an experiment (exposures, conversions, etc.)."""

    __tablename__ = "experiment_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    experiment_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Company that triggered the event
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    # Event type: "exposed", "converted", etc.
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Variant that was active when event occurred
    variant: Mapped[str] = mapped_column(String(50), nullable=False)

    # Event metadata stored as JSON
    event_metadata: Mapped[object | None] = mapped_column(JSONType, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationship
    experiment = relationship("Experiment", back_populates="events")

    __table_args__ = (
        Index("ix_experiment_events_experiment_id", "experiment_id"),
        Index("ix_experiment_events_company_id", "company_id"),
        Index("ix_experiment_events_event_type", "event_type"),
        Index("ix_experiment_events_created_at", "created_at"),
        Index(
            "ix_experiment_events_experiment_variant",
            "experiment_id",
            "variant",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ExperimentEvent(experiment={self.experiment_id}, "
            f"type={self.event_type}, variant={self.variant})>"
        )


# Module exports
__all__ = [
    "Experiment",
    "ExperimentVariant",
    "ExperimentAssignment",
    "ExperimentEvent",
]
