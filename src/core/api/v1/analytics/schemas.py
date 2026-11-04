"""
Pydantic schemas for Analytics API.

Request and response models for cross-company benchmarking endpoints.
All responses contain only anonymized, k-anonymous data.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# Sector Benchmark Schemas
# ============================================================================


class PackBenchmarkData(BaseModel):
    """Benchmark data for a single pack in a sector."""

    model_config = ConfigDict(from_attributes=True)

    pack_id: str = Field(description="Domain pack identifier")
    pack_name: str | None = Field(default=None, description="Human-readable pack name")
    adoption_rate_pct: float = Field(
        description="Percentage of companies in sector using this pack (0-100)"
    )
    active_companies: int = Field(description="Number of companies actively using this pack")
    total_companies: int = Field(description="Total companies in sector (k-anonymity check)")
    total_activations: int = Field(description="Cumulative total activations")
    avg_usage_per_company: float = Field(description="Average usage events per active company")
    rank: int = Field(description="Rank by adoption rate in sector")


class SectorBenchmarksResponse(BaseModel):
    """Response schema for sector benchmarking data."""

    sector: str = Field(description="Industry sector")
    company_type: str = Field(description="Company type filter (mkb, zzp, enterprise, all)")
    date: datetime = Field(description="Date of aggregation data")
    total_companies: int = Field(description="Total companies in this sector")
    packs: list[PackBenchmarkData] = Field(description="Pack benchmarks, sorted by adoption rate")
    k_anonymity_met: bool = Field(description="Whether k-anonymity threshold is met")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Company Comparison Schemas
# ============================================================================


class CompanyPackComparison(BaseModel):
    """Comparison data for a pack between company and sector."""

    pack_id: str = Field(description="Domain pack identifier")
    pack_name: str | None = Field(default=None, description="Human-readable pack name")
    company_has_pack: bool = Field(description="Whether the company uses this pack")
    sector_adoption_rate_pct: float = Field(description="Sector adoption rate (0-100)")
    sector_avg_usage: float = Field(description="Sector average usage per company")

    model_config = ConfigDict(from_attributes=True)


class CompanyComparisonResponse(BaseModel):
    """Response schema for company vs sector comparison."""

    company_id_hash: str = Field(description="Anonymized company identifier")
    sector: str = Field(description="Company's industry sector")
    company_type: str = Field(description="Company type")

    # Adoption metrics
    total_packs_active: int = Field(description="Number of packs company uses")
    sector_avg_packs: float = Field(description="Sector average packs per company")
    percentile: int = Field(description="Percentile rank (0-100, e.g., 75 means top 25%)")

    # Detailed comparison
    pack_comparisons: list[CompanyPackComparison] = Field(
        description="Detailed pack-by-pack comparison"
    )

    # Privacy notice
    k_anonymity_met: bool = Field(description="Whether comparison data is k-anonymous")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Trend Schemas
# ============================================================================


class PackTrendData(BaseModel):
    """Trend data for a pack over time."""

    date: datetime = Field(description="Date of data point")
    adoption_rate_pct: float = Field(description="Adoption rate on this date")
    active_companies: int = Field(description="Number of active companies")
    daily_activations: int = Field(description="New activations on this date")

    model_config = ConfigDict(from_attributes=True)


class PackTrendsResponse(BaseModel):
    """Response schema for pack adoption trends."""

    pack_id: str = Field(description="Domain pack identifier")
    sector: str = Field(description="Industry sector")
    date_range_days: int = Field(description="Number of days in trend data")
    trends: list[PackTrendData] = Field(description="Daily trend data points")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Opt-out Schemas
# ============================================================================


class OptOutRequest(BaseModel):
    """Request to opt out of cross-company analytics."""

    reason: str | None = Field(
        default=None, max_length=500, description="Optional reason for opting out"
    )


class OptOutResponse(BaseModel):
    """Response for opt-out request."""

    company_id: str = Field(description="Company ID (shown once)")
    opted_out_at: datetime = Field(description="Timestamp of opt-out")
    message: str = Field(description="Confirmation message")

    model_config = ConfigDict(from_attributes=True)


class OptOutStatusResponse(BaseModel):
    """Response for opt-out status check."""

    company_id: str = Field(description="Company ID")
    opted_out: bool = Field(description="Whether company has opted out")
    opted_out_at: datetime | None = Field(default=None, description="Opt-out timestamp")

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Error Responses
# ============================================================================


class KAnonymityErrorResponse(BaseModel):
    """Error response when k-anonymity is not met."""

    error: str = Field(default="k_anonymity_not_met")
    message: str = Field(description="Human-readable error message")
    sector: str = Field(description="Sector that failed k-anonymity check")
    company_count: int = Field(description="Number of companies in sector")
    required_count: int = Field(default=5, description="Required companies for k-anonymity")

    model_config = ConfigDict(from_attributes=True)
