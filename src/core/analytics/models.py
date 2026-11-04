"""
Analytics Data Models - Event ingestion and metrics storage
Production-ready schema for analytics event persistence and querying
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class AnalyticsEvent(Base):  # type: ignore[misc]
    """
    Immutable Analytics Event record for frontend and backend events.
    Supports batch ingestion, multi-tenant isolation, and GDPR compliance.
    """

    __tablename__ = "analytics_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    # Session and user tracking
    session_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    # Event classification
    event_type: Mapped[str] = mapped_column(
        String(50), index=True, nullable=False
    )  # user_action, performance, error, etc.
    event_subtype: Mapped[str | None] = mapped_column(
        String(100), index=True, nullable=True
    )  # workflow_created, etc.
    severity: Mapped[str] = mapped_column(
        String(20), default="MEDIUM", index=True, nullable=False
    )  # LOW, MEDIUM, HIGH, CRITICAL

    # Event data
    event_data: Mapped[dict[str, Any]] = mapped_column(JSON, default={}, nullable=False)  # TODO(TYPE): replace Any with concrete type

    # Context
    context: Mapped[dict[str, Any] | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=True
    )  # Browser, OS, device info

    # Timestamps
    event_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    # Batch tracking
    batch_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    # Retention fields (for GDPR compliance)
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Indexes for common query patterns
    __table_args__ = (
        Index("ix_analytics_events_tenant_timestamp", "tenant_id", "event_timestamp"),
        Index("ix_analytics_events_session_type", "session_id", "event_type"),
        Index("ix_analytics_events_user_timestamp", "user_id", "event_timestamp"),
        Index("ix_analytics_events_batch", "batch_id"),
    )


class AnalyticsMetric(Base):  # type: ignore[misc]
    """
    Pre-aggregated metrics for performance and analytics dashboards.
    Computed from raw events for efficient querying.
    """

    __tablename__ = "analytics_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    # Metric identification
    metric_type: Mapped[str] = mapped_column(
        String(100), index=True, nullable=False
    )  # lcp, api_latency, error_rate, etc.
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Aggregation period
    aggregation_level: Mapped[str] = mapped_column(
        String(20), default="hourly", index=True
    )  # hourly, daily, weekly, monthly
    time_bucket: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )

    # Metric values
    value_count: Mapped[int] = mapped_column(Integer, default=0)
    value_sum: Mapped[float] = mapped_column(Float, default=0.0)
    value_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_p50: Mapped[float | None] = mapped_column(Float, nullable=True)  # Median
    value_p95: Mapped[float | None] = mapped_column(Float, nullable=True)  # 95th percentile
    value_p99: Mapped[float | None] = mapped_column(Float, nullable=True)  # 99th percentile

    # Dimensions for filtering
    dimensions: Mapped[dict[str, str] | None] = mapped_column(
        JSON, nullable=True
    )  # workflow_id, agent_type, etc.

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index("ix_metrics_tenant_type_bucket", "tenant_id", "metric_type", "time_bucket"),
        Index("ix_metrics_tenant_bucket", "tenant_id", "time_bucket"),
    )


class AnalyticsSession(Base):  # type: ignore[misc]
    """
    Session summary for user analytics.
    Aggregated from session_start and session_end events.
    """

    __tablename__ = "analytics_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    # Session identification
    session_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    # Session metrics
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Activity counts
    page_view_count: Mapped[int] = mapped_column(Integer, default=0)
    event_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # Actions performed (stored as JSON list)
    actions: Mapped[dict[str, Any] | None] = mapped_column(JSON, default={}, nullable=True)  # TODO(TYPE): replace Any with concrete type

    # Device and browser
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Session status
    is_active: Mapped[bool] = mapped_column(default=True, index=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Indexes
    __table_args__ = (
        Index("ix_sessions_tenant_user", "tenant_id", "user_id"),
        Index("ix_sessions_tenant_start", "tenant_id", "start_time"),
    )
