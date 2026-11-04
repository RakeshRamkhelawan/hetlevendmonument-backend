"""
Benchmarking API - Cross-company pack usage analytics

Provides privacy-preserving benchmarking endpoints for comparing
pack usage across companies. All data is k-anonymous (minimum 5
companies per sector) and anonymized (no PII).

Endpoints:
    GET /analytics/benchmarks/sectors - List available sectors
    GET /analytics/benchmarks/sector/{sector} - Get sector benchmarks
    GET /analytics/benchmarks/compare/{company_id} - Compare company to sector
    GET /analytics/benchmarks/trends/{pack_id} - Get pack adoption trends
    POST /analytics/benchmarks/opt-out - Opt out of analytics
    GET /analytics/benchmarks/opt-out/status - Check opt-out status

Privacy Features:
    - k-anonymity enforced (sectors with <5 companies return error)
    - Company IDs hashed in responses
    - Opt-out supported
    - Query logging for compliance

Usage:
    # Get sector benchmarks
    GET /api/v1/analytics/benchmarks/sector/Technology

    # Compare company to sector
    GET /api/v1/analytics/benchmarks/compare/{company_id}

    # Get pack trends
    GET /api/v1/analytics/benchmarks/trends/pack-123?sector=Technology&days=30
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.analytics.anonymizer import DataAnonymizer
from src.core.api.v1.analytics.schemas import (
    CompanyComparisonResponse,
    CompanyPackComparison,
    KAnonymityErrorResponse,
    OptOutRequest,
    OptOutResponse,
    OptOutStatusResponse,
    PackBenchmarkData,
    PackTrendData,
    PackTrendsResponse,
    SectorBenchmarksResponse,
)
from src.core.api.v1.analytics.dependencies import (
    BenchmarkingQueryLog,
    CompanyAnalyticsOptOut,
    PackUsageAggregate,
    get_db_session,
)
from src.core.auth.api_deps import get_current_user
from src.core.company.models import Company, Department
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/analytics/benchmarks",
    tags=["Analytics - Benchmarking"],
)

# k-anonymity threshold
K_ANONYMITY_THRESHOLD = 5


async def log_benchmark_query(
    db: AsyncSession,
    user_id: int,
    company_id: UUID | None,
    query_type: str,
    query_params: str,
) -> None:
    """Log benchmarking query for compliance audit."""
    log_entry = BenchmarkingQueryLog(
        user_id=user_id,
        company_id=company_id,
        query_type=query_type,
        query_params=query_params,
    )
    db.add(log_entry)
    await db.commit()


async def check_sector_k_anonymity(
    db: AsyncSession, sector: str, company_type: str | None = None
) -> tuple[bool, int]:
    """
    Check if a sector meets k-anonymity requirements.

    Returns:
        Tuple of (meets_k_anonymity, company_count)
    """
    query = select(func.count(Company.id)).where(
        and_(
            Company.sector == sector,
            Company.status == "active",
        )
    )

    if company_type:
        query = query.where(Company.company_type == company_type)

    result = await db.execute(query)
    count = result.scalar() or 0

    return count >= K_ANONYMITY_THRESHOLD, count


async def get_opted_out_company_ids(db: AsyncSession) -> set[UUID]:
    """Get set of company IDs that have opted out."""
    result = await db.execute(select(CompanyAnalyticsOptOut.company_id))
    return {row[0] for row in result.all()}


@router.get(
    "/sectors",
    response_model=list[str],
    summary="List available sectors for benchmarking",
    description="Returns list of sectors with k-anonymous data available.",
)
async def list_available_sectors(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[str]:
    """
    List sectors that have sufficient data for benchmarking.

    Only sectors with k-anonymity (>=5 companies) are returned.
    """
    # Get sectors with k-anonymous aggregations
    result = await db.execute(
        select(PackUsageAggregate.sector)
        .where(PackUsageAggregate.k_anonymity_met.is_(True))
        .distinct()
        .order_by(PackUsageAggregate.sector)
    )

    sectors = [row[0] for row in result.all()]

    # Log query
    await log_benchmark_query(db, current_user.id, None, "list_sectors", "")

    return sectors


@router.get(
    "/sector/{sector}",
    response_model=SectorBenchmarksResponse,
    summary="Get pack benchmarks for a sector",
    description="Returns pack usage statistics for companies in the specified sector.",
    responses={
        404: {"description": "Sector not found or insufficient data"},
        412: {"model": KAnonymityErrorResponse, "description": "k-anonymity not met"},
    },
)
async def get_sector_benchmarks(
    sector: str,
    company_type: str | None = Query(
        None, description="Filter by company type (mkb, zzp, enterprise)"
    ),
    date: datetime | None = Query(None, description="Date for data (defaults to latest)"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> SectorBenchmarksResponse:
    """
    Get pack adoption benchmarks for a specific sector.

    Returns pack usage statistics comparing adoption rates across
    companies in the sector. Data is k-anonymous (>=5 companies).

    Args:
        sector: Industry sector name
        company_type: Optional filter by company type
        date: Optional specific date (defaults to most recent)

    Returns:
        SectorBenchmarksResponse with pack rankings

    Raises:
        HTTPException 404: If sector not found
        HTTPException 412: If k-anonymity not met
    """
    # Check k-anonymity
    meets_k, company_count = await check_sector_k_anonymity(db, sector, company_type)

    if not meets_k:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "error": "k_anonymity_not_met",
                "message": f"Sector '{sector}' has insufficient companies for anonymous benchmarking",
                "sector": sector,
                "company_count": company_count,
                "required_count": K_ANONYMITY_THRESHOLD,
            },
        )

    # Get query date
    if date is None:
        # Get latest available date
        date_result = await db.execute(
            select(func.max(PackUsageAggregate.date)).where(PackUsageAggregate.sector == sector)
        )
        date = date_result.scalar()

        if date is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No benchmark data available for sector '{sector}'",
            )

    # Build query
    query = select(PackUsageAggregate).where(
        and_(
            PackUsageAggregate.sector == sector,
            PackUsageAggregate.date == date,
            PackUsageAggregate.k_anonymity_met.is_(True),
        )
    )

    if company_type:
        query = query.where(PackUsageAggregate.company_type == company_type)

    query = query.order_by(desc(PackUsageAggregate.adoption_rate_pct))

    result = await db.execute(query)
    aggregates = result.scalars().all()

    if not aggregates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No benchmark data for sector '{sector}' on {date.date()}",
        )

    # Build pack benchmarks
    packs = []
    total_companies = 0

    for rank, agg in enumerate(aggregates, 1):
        packs.append(
            PackBenchmarkData(
                pack_id=agg.pack_id,
                pack_name=agg.pack_name,
                adoption_rate_pct=round(agg.adoption_rate_pct, 2),
                active_companies=agg.active_companies,
                total_companies=agg.total_companies,
                total_activations=agg.total_activations,
                avg_usage_per_company=round(agg.avg_usage_per_company, 2),
                rank=rank,
            )
        )
        total_companies = max(total_companies, agg.total_companies)

    # Log query
    await log_benchmark_query(
        db,
        current_user.id,
        None,
        "sector_benchmarks",
        f"sector={sector},type={company_type},date={date.date()}",
    )

    return SectorBenchmarksResponse(
        sector=sector,
        company_type=company_type or "all",
        date=date,
        total_companies=total_companies,
        packs=packs,
        k_anonymity_met=True,
    )


@router.get(
    "/compare/{company_id}",
    response_model=CompanyComparisonResponse,
    summary="Compare company to sector average",
    description="Returns comparison of company's pack usage vs sector benchmarks.",
    responses={
        404: {"description": "Company not found"},
        412: {
            "model": KAnonymityErrorResponse,
            "description": "k-anonymity not met for sector",
        },
    },
)
async def compare_company_to_sector(
    company_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> CompanyComparisonResponse:
    """
    Compare a company's pack usage to sector benchmarks.

    Returns percentile ranking and detailed pack-by-pack comparison.
    Company ID in response is hashed for privacy.

    Args:
        company_id: Company UUID to compare

    Returns:
        CompanyComparisonResponse with percentile and comparisons

    Raises:
        HTTPException 404: If company not found
        HTTPException 412: If sector k-anonymity not met
    """
    # Get company
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Company {company_id} not found",
        )

    # Check if opted out
    opted_out_ids = await get_opted_out_company_ids(db)
    if company.id in opted_out_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company has opted out of benchmarking analytics",
        )

    # Check k-anonymity for sector
    meets_k, company_count = await check_sector_k_anonymity(
        db, company.sector, company.company_type
    )

    if not meets_k:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={
                "error": "k_anonymity_not_met",
                "message": f"Sector '{company.sector}' has insufficient companies for comparison",
                "sector": company.sector,
                "company_count": company_count,
                "required_count": K_ANONYMITY_THRESHOLD,
            },
        )

    # Get company's active packs from departments
    result = await db.execute(select(Department).where(Department.company_id == company_id))
    departments = result.scalars().all()

    company_pack_ids = set()
    for dept in departments:
        if dept.domain_pack_ids:
            company_pack_ids.update(dept.domain_pack_ids)

    # Get latest sector aggregates
    date_result = await db.execute(
        select(func.max(PackUsageAggregate.date)).where(PackUsageAggregate.sector == company.sector)
    )
    latest_date: datetime | None = date_result.scalar()

    if latest_date is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No benchmark data available for sector '{company.sector}'",
        )

    # Get sector benchmarks
    result = await db.execute(
        select(PackUsageAggregate).where(
            and_(
                PackUsageAggregate.sector == company.sector,
                PackUsageAggregate.date == latest_date,
                PackUsageAggregate.company_type == company.company_type,
            )
        )
    )
    sector_aggregates = result.scalars().all()

    # Build pack comparisons
    pack_comparisons = []
    total_sector_packs = len(sector_aggregates)
    company_packs_in_sector = 0

    for agg in sector_aggregates:
        has_pack = agg.pack_id in company_pack_ids
        if has_pack:
            company_packs_in_sector += 1

        pack_comparisons.append(
            CompanyPackComparison(
                pack_id=agg.pack_id,
                pack_name=agg.pack_name,
                company_has_pack=has_pack,
                sector_adoption_rate_pct=round(agg.adoption_rate_pct, 2),
                sector_avg_usage=round(agg.avg_usage_per_company, 2),
            )
        )

    # Calculate percentile
    # Simple percentile: how many packs does company use vs sector average
    sector_avg_packs = sum(agg.active_companies for agg in sector_aggregates) / max(
        sum(agg.total_companies for agg in sector_aggregates), 1
    )

    # Percentile based on pack adoption rate
    if total_sector_packs > 0:
        adoption_rate = company_packs_in_sector / total_sector_packs
        # Convert to percentile (0-100, higher is better)
        percentile = int(adoption_rate * 100)
    else:
        percentile = 0
        adoption_rate = 0

    # Hash company ID for response
    company_hash = DataAnonymizer.hash_company_id(str(company_id))

    # Log query
    await log_benchmark_query(
        db,
        current_user.id,
        None,
        "company_comparison",
        f"company_hash={company_hash},sector={company.sector}",
    )

    return CompanyComparisonResponse(
        company_id_hash=company_hash,
        sector=company.sector,
        company_type=company.company_type,
        total_packs_active=len(company_pack_ids),
        sector_avg_packs=round(sector_avg_packs, 2),
        percentile=percentile,
        pack_comparisons=pack_comparisons,
        k_anonymity_met=True,
    )


@router.get(
    "/trends/{pack_id}",
    response_model=PackTrendsResponse,
    summary="Get pack adoption trends over time",
    description="Returns historical adoption trends for a pack in a sector.",
)
async def get_pack_trends(
    pack_id: str,
    sector: str = Query(..., description="Industry sector"),
    days: int = Query(30, ge=7, le=365, description="Number of days of history"),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> PackTrendsResponse:
    """
    Get historical adoption trends for a pack.

    Args:
        pack_id: Pack identifier
        sector: Industry sector
        days: Number of days of history (7-365)

    Returns:
        PackTrendsResponse with daily trend data
    """
    # Calculate date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get trend data
    result = await db.execute(
        select(PackUsageAggregate)
        .where(
            and_(
                PackUsageAggregate.pack_id == pack_id,
                PackUsageAggregate.sector == sector,
                PackUsageAggregate.date >= start_date,
                PackUsageAggregate.k_anonymity_met.is_(True),
            )
        )
        .order_by(PackUsageAggregate.date)
    )
    aggregates = result.scalars().all()

    trends = [
        PackTrendData(
            date=agg.date,
            adoption_rate_pct=round(agg.adoption_rate_pct, 2),
            active_companies=agg.active_companies,
            daily_activations=agg.daily_activations,
        )
        for agg in aggregates
    ]

    # Log query
    await log_benchmark_query(
        db,
        current_user.id,
        None,
        "pack_trends",
        f"pack_id={pack_id},sector={sector},days={days}",
    )

    return PackTrendsResponse(
        pack_id=pack_id,
        sector=sector,
        date_range_days=days,
        trends=trends,
    )


@router.post(
    "/opt-out",
    response_model=OptOutResponse,
    summary="Opt out of cross-company analytics",
    description="Remove company data from future benchmarking aggregations.",
)
async def opt_out_of_analytics(
    request: OptOutRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> OptOutResponse:
    """
    Opt out of cross-company analytics.

    Company's data will be excluded from future aggregations.
    Previously aggregated data may remain until retention period expires.

    Args:
        request: OptOutRequest with optional reason

    Returns:
        OptOutResponse confirming opt-out
    """
    # Get user's company (from tenant context)
    # For now, we need a company_id - this would come from context or parameter
    # This is a simplified implementation

    # In real implementation, get company from user's tenant context
    result = await db.execute(select(Company).where(Company.tenant_id == current_user.tenant_id))
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company found for current user",
        )

    # Check if already opted out
    result = await db.execute(
        select(CompanyAnalyticsOptOut).where(CompanyAnalyticsOptOut.company_id == company.id)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return OptOutResponse(
            company_id=str(company.id),
            opted_out_at=existing.opted_out_at,
            message="Company was already opted out of analytics",
        )

    # Create opt-out record
    company_hash = DataAnonymizer.hash_company_id(str(company.id))
    opt_out = CompanyAnalyticsOptOut(
        company_id=company.id,
        reason=request.reason,
        company_hash=company_hash,
    )

    db.add(opt_out)

    # Update company config
    if not isinstance(company.config, dict):
        company.config = {}
    company.config["opt_out_analytics"] = True

    await db.commit()

    logger.info("Company %s opted out of analytics", company.id)

    return OptOutResponse(
        company_id=str(company.id),
        opted_out_at=opt_out.opted_out_at,
        message="Successfully opted out of cross-company analytics",
    )


@router.get(
    "/opt-out/status",
    response_model=OptOutStatusResponse,
    summary="Check opt-out status",
    description="Check if company has opted out of analytics.",
)
async def get_opt_out_status(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> OptOutStatusResponse:
    """
    Check if the current user's company has opted out.

    Returns:
        OptOutStatusResponse with opt-out status
    """
    # Get user's company
    result = await db.execute(select(Company).where(Company.tenant_id == current_user.tenant_id))
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No company found for current user",
        )

    # Check opt-out status
    result = await db.execute(
        select(CompanyAnalyticsOptOut).where(CompanyAnalyticsOptOut.company_id == company.id)
    )
    opt_out = result.scalar_one_or_none()

    # Also check config
    config_opt_out = False
    if isinstance(company.config, dict):
        config_opt_out = company.config.get("opt_out_analytics", False)

    opted_out = opt_out is not None or config_opt_out

    return OptOutStatusResponse(
        company_id=str(company.id),
        opted_out=opted_out,
        opted_out_at=opt_out.opted_out_at if opt_out else None,
    )
