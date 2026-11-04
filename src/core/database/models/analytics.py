"""
Analytics Models for Cross-Company Benchmarking

Database models for storing aggregated, anonymized pack usage statistics.
All data stored here is already anonymized and k-anonymous compliant.

Models:
- PackUsageAggregate: Daily aggregated pack usage by sector
- CompanyAnalyticsOptOut: Companies that opted out of analytics

GDPR Notes:
- No PII stored in these tables
- Company IDs are hashed (irreversible)
- Opt-out respected at aggregation time
- Data retention policy: 2 years (configurable)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from src.core.database.database import Base


class PackUsageAggregate(Base):  # type: ignore[misc]
    """
    Daily aggregated pack usage statistics by sector.

    This table stores pre-computed, anonymized aggregations of pack usage
    for efficient benchmarking queries. All data is k-anonymous (minimum
    5 companies per sector).

    Aggregation happens daily at 04:00 AM via analytics_aggregation job.

    Attributes:
        id: Primary key
        date: Date of aggregation (daily granularity)
        sector: Industry sector (e.g., "Technology", "Healthcare")
        company_type: Company type (mkb, zzp, enterprise)
        employee_bucket: Employee size bucket (1-9, 10-49, 50-249, 250+)
        pack_id: Domain pack identifier
        total_companies: Total companies in this sector/bucket
        active_companies: Companies actively using this pack
        total_activations: Total pack activations (all time cumulative)
        daily_activations: New activations on this date
        adoption_rate_pct: Percentage of companies using this pack
        avg_usage_per_company: Average usage events per active company
    """

    __tablename__ = "pack_usage_aggregates"

    # Primary key
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Aggregation date (daily)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Dimensions
    sector: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Industry sector for grouping"
    )
    company_type: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True, comment="mkb, zzp, or enterprise"
    )
    employee_bucket: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Employee count bucket: 1-9, 10-49, 50-249, 250+",
    )

    # Pack identifier
    pack_id: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Domain pack identifier"
    )
    pack_name: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="Human-readable pack name"
    )

    # Metrics
    total_companies: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Total companies in this sector/bucket (k-anonymity check)",
    )
    active_companies: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of companies actively using this pack",
    )
    total_activations: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Cumulative total pack activations"
    )
    daily_activations: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="New activations on this specific date",
    )
    adoption_rate_pct: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Percentage of companies using this pack (0-100)",
    )
    avg_usage_per_company: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
        comment="Average usage events per active company",
    )

    # k-anonymity metadata
    k_anonymity_met: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether k-anonymity (>=5 companies) is satisfied",
    )

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

    __table_args__ = (
        # Primary lookup: sector + date for benchmarking queries
        Index("idx_pack_usage_sector_date", "sector", "date", postgresql_using="btree"),
        # Pack performance lookup
        Index("idx_pack_usage_pack_date", "pack_id", "date", postgresql_using="btree"),
        # Company type filtering
        Index(
            "idx_pack_usage_type_sector",
            "company_type",
            "sector",
            postgresql_using="btree",
        ),
        # k-anonymity check index
        Index("idx_pack_usage_k_anon", "k_anonymity_met", "total_companies"),
        # Unique constraint to prevent duplicate aggregations
        Index(
            "idx_pack_usage_unique",
            "date",
            "sector",
            "company_type",
            "employee_bucket",
            "pack_id",
            unique=True,
        ),
        {"comment": "Daily aggregated pack usage statistics (anonymized)"},
    )

    def __repr__(self) -> str:
        return (
            f"<PackUsageAggregate({self.sector}, {self.pack_id}, "
            f"{self.date.strftime('%Y-%m-%d')}, {self.adoption_rate_pct:.1f}%)>"
        )


class CompanyAnalyticsOptOut(Base):  # type: ignore[misc]
    """
    Track companies that have opted out of cross-company analytics.

    GDPR compliance: Companies can opt-out of having their data
    included in benchmarking aggregations.

    Note: Opt-out is checked during aggregation, not query time,
    to ensure no data from opted-out companies is ever stored
    in analytics tables.
    """

    __tablename__ = "company_analytics_opt_out"

    # Primary key - company ID
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, comment="Company that opted out"
    )

    # Opt-out metadata
    opted_out_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Optional reason for opt-out"
    )

    # For audit purposes (hashed, not reversible)
    company_hash: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        index=True,
        comment="Hashed company ID for trend removal",
    )

    __table_args__ = ({"comment": "Companies opted out of analytics (GDPR compliance)"},)

    def __repr__(self) -> str:
        return f"<CompanyAnalyticsOptOut({self.company_hash}, {self.opted_out_at})>"


class BenchmarkingQueryLog(Base):  # type: ignore[misc]
    """
    Audit log for benchmarking queries.

    Tracks who queried benchmarking data and when for compliance.
    No actual query results stored, just metadata.
    """

    __tablename__ = "benchmarking_query_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Query metadata
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)

    # Query parameters (not results)
    query_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of query: sector_benchmarks, company_comparison, etc.",
    )
    query_params: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Query parameters (sector, date range, etc.)",
    )

    # Timing
    queried_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_benchmark_log_user", "user_id", "queried_at"),
        Index("idx_benchmark_log_company", "company_id", "queried_at"),
        {"comment": "Audit log for benchmarking queries (GDPR compliance)"},
    )


# Module exports
__all__ = [
    "PackUsageAggregate",
    "CompanyAnalyticsOptOut",
    "BenchmarkingQueryLog",
]
