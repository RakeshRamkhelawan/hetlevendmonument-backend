"""
Analytics Aggregation Job

Daily background job that aggregates pack usage data for benchmarking.
Runs at 04:00 AM after ML training job completes.

Process:
1. Load all active companies
2. Filter out opted-out companies
3. Anonymize company data
4. Group by sector and check k-anonymity (>=5 companies)
5. Aggregate pack usage by sector/company_type/employee_bucket
6. Store aggregated results

Privacy Features:
- k-anonymity enforcement (sectors with <5 companies excluded)
- Company IDs hashed before storage
- PII never stored in analytics tables
- Opt-out respected at aggregation time

Usage:
    # Manual run
    from src.core.jobs.analytics_aggregation import run_analytics_aggregation
    await run_analytics_aggregation()

    # Scheduled (via Dramatiq or cron)
    # 0 4 * * * python -m src.core.jobs.analytics_aggregation
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.analytics.anonymizer import DataAnonymizer
from src.core.company.models import Company, Department
from src.core.database.models.analytics import PackUsageAggregate
from src.core.database.session import get_db_session
from src.core.procedures.models import (
    PackActivationAuditLog,
)  # NOTE: re-exported from procedures.models

logger = logging.getLogger(__name__)

#: Bewust UIT: `pack_usage_aggregates.pack_id` is in de database een UUID met een verwijzing naar
#: `domain_packs` (per klant, vaste UUID per rij), terwijl deze job een pakketSLEUTEL als tekst
#: kent (`pack_activation_audit_logs.pack_id`). Zonder pakketcatalogus met vaste id's bestaat er
#: geen koppeling, en de aggregaten lopen bewust over klanten heen. Elke insert faalde op
#: `column "pack_id" is of type uuid but expression is of type character varying` (gemeten
#: 2026-10-23, docs/backend/schemadrift-indeling-2026-10-23.md). Ontwerpkeuze, eventueel met
#: migratie, later; niet nodig voor de pilot.
SCHRIJF_PACK_USAGE_AGGREGATEN = False
UITGESCHAKELD_REDEN = (
    "pack_usage_aggregates uitgeschakeld tot een catalogustabel met vaste id's bestaat"
)

# Minimum companies per sector for k-anonymity
K_ANONYMITY_THRESHOLD = 5


async def get_active_companies(db: AsyncSession) -> list[Company]:
    """
    Get all active companies for aggregation.

    Args:
        db: Database session

    Returns:
        List of active Company objects
    """
    result = await db.execute(select(Company).where(Company.status == "active"))
    return list(result.scalars().all())


async def get_opted_out_company_ids(db: AsyncSession) -> set[Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get set of company IDs that have opted out of analytics.

    Args:
        db: Database session

    Returns:
        Set of company UUIDs that opted out
    """
    from src.core.database.models.analytics import CompanyAnalyticsOptOut

    result = await db.execute(select(CompanyAnalyticsOptOut.company_id))
    return {row[0] for row in result.all()}


async def get_pack_usage_for_date(
    db: AsyncSession, date: datetime
) -> dict[tuple[str, Any], dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Get pack usage data for a specific date.

    Returns usage aggregated by company and pack.

    Args:
        db: Database session
        date: Date to query for

    Returns:
        Dictionary mapping (company_id, pack_id) to usage stats
    """
    start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    result = await db.execute(
        select(
            PackActivationAuditLog.company_id,
            PackActivationAuditLog.pack_id,
            func.count(PackActivationAuditLog.id).label("usage_count"),
        )
        .where(
            and_(
                PackActivationAuditLog.created_at >= start_of_day,
                PackActivationAuditLog.created_at < end_of_day,
            )
        )
        .group_by(
            PackActivationAuditLog.company_id,
            PackActivationAuditLog.pack_id,
        )
    )

    usage_data = {}
    for row in result.all():
        key = (str(row.company_id), row.pack_id)
        usage_data[key] = {
            "usage_count": row.usage_count,
        }

    return usage_data


async def get_cumulative_pack_usage(
    db: AsyncSession, as_of_date: datetime
) -> dict[tuple[str, Any], int]:  # TODO(TYPE): replace Any with concrete type
    """
    Get cumulative pack usage up to a specific date.

    Args:
        db: Database session
        as_of_date: Calculate totals up to this date

    Returns:
        Dictionary mapping (company_id, pack_id) to cumulative counts
    """
    result = await db.execute(
        select(
            PackActivationAuditLog.company_id,
            PackActivationAuditLog.pack_id,
            func.count(PackActivationAuditLog.id).label("total_activations"),
        )
        .where(PackActivationAuditLog.created_at < as_of_date)
        .group_by(
            PackActivationAuditLog.company_id,
            PackActivationAuditLog.pack_id,
        )
    )

    cumulative = {}
    for row in result.all():
        key = (str(row.company_id), row.pack_id)
        cumulative[key] = row.total_activations

    return cumulative


def group_companies_by_sector(
    companies: list[Company], opted_out_ids: set[Any]  # TODO(TYPE): replace Any with concrete type
) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
    """
    Group companies by sector, excluding opted-out companies.

    Args:
        companies: List of Company objects
        opted_out_ids: Set of company IDs that opted out

    Returns:
        Dictionary mapping sector to list of anonymized company data
    """
    sector_groups: dict[str, list[dict[str, Any]]] = {}  # TODO(TYPE): replace Any with concrete type

    for company in companies:
        # Skip opted-out companies
        if company.id in opted_out_ids:
            continue

        # Check company config for opt-out
        if isinstance(company.config, dict) and company.config.get("opt_out_analytics", False):
            continue

        sector = company.sector
        if not sector:
            continue

        # Anonymize company data
        company_dict = {
            "id": str(company.id),
            "sector": company.sector,
            "company_type": company.company_type,
            "config": company.config if isinstance(company.config, dict) else {},
        }

        anonymized = DataAnonymizer.anonymize_company(company_dict)

        if sector not in sector_groups:
            sector_groups[sector] = []
        sector_groups[sector].append(anonymized)

    return sector_groups


def filter_k_anonymous_sectors(
    sector_groups: dict[str, list[dict[str, Any]]],  # TODO(TYPE): replace Any with concrete type
) -> dict[str, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
    """
    Filter sectors to only include those with k-anonymity.

    k-anonymity requires at least K_ANONYMITY_THRESHOLD companies
    in a sector to prevent identification.

    Args:
        sector_groups: Dictionary mapping sector to companies

    Returns:
        Filtered dictionary with only k-anonymous sectors
    """
    return {
        sector: companies
        for sector, companies in sector_groups.items()
        if len(companies) >= K_ANONYMITY_THRESHOLD
    }


async def get_department_packs_for_sector(
    db: AsyncSession, sector: str, opted_out_ids: set[Any]  # TODO(TYPE): replace Any with concrete type
) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Get all pack activations for companies in a sector.

    Args:
        db: Database session
        sector: Industry sector
        opted_out_ids: Set of company IDs to exclude

    Returns:
        Dictionary with pack usage statistics
    """
    # Get companies in sector
    result = await db.execute(
        select(Company.id).where(
            and_(
                Company.sector == sector,
                Company.status == "active",
            )
        )
    )
    company_ids = [row[0] for row in result.all() if row[0] not in opted_out_ids]

    if not company_ids:
        return {}

    # Get departments for these companies
    dept_result = await db.execute(select(Department).where(Department.company_id.in_(company_ids)))
    departments: list[Department] = list(dept_result.scalars().all())

    # Aggregate pack usage
    pack_stats: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    for dept in departments:
        if not dept.domain_pack_ids:
            continue

        for pack_id in dept.domain_pack_ids:
            if pack_id not in pack_stats:
                pack_stats[pack_id] = {
                    "total_companies": set(),
                    "total_activations": 0,
                }
            pack_stats[pack_id]["total_companies"].add(str(dept.company_id))
            pack_stats[pack_id]["total_activations"] += 1

    # Convert sets to counts
    for pack_id in pack_stats:
        pack_stats[pack_id]["total_companies"] = len(pack_stats[pack_id]["total_companies"])

    return pack_stats


async def aggregate_sector_data(
    db: AsyncSession,
    sector: str,
    companies: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
    aggregation_date: datetime,
    opted_out_ids: set[Any],  # TODO(TYPE): replace Any with concrete type
) -> list[PackUsageAggregate]:
    """
    Create aggregation records for a sector.

    Args:
        db: Database session
        sector: Industry sector name
        companies: List of anonymized companies in sector
        aggregation_date: Date for aggregation
        opted_out_ids: Set of opted-out company IDs

    Returns:
        List of PackUsageAggregate records to save
    """
    # Get pack usage for sector
    pack_stats = await get_department_packs_for_sector(db, sector, opted_out_ids)

    if not pack_stats:
        return []

    # Get daily usage
    daily_usage = await get_pack_usage_for_date(db, aggregation_date)
    cumulative_usage = await get_cumulative_pack_usage(db, aggregation_date + timedelta(days=1))

    # Calculate total companies in sector
    total_companies = len(companies)

    aggregates = []

    for pack_id, stats in pack_stats.items():
        # Calculate metrics
        active_companies = stats["total_companies"]
        total_activations = stats["total_activations"]

        # Calculate adoption rate
        adoption_rate_pct = (active_companies / total_companies * 100) if total_companies > 0 else 0

        # Calculate daily activations (from audit logs)
        daily_activations = sum(1 for key in daily_usage if key[1] == pack_id)

        # Calculate cumulative from audit logs
        cumulative = (
            sum(count for key, count in cumulative_usage.items() if key[1] == pack_id)
            if cumulative_usage
            else total_activations
        )

        # Calculate average usage per company
        avg_usage = cumulative / active_companies if active_companies > 0 else 0

        # Group by company type and employee bucket
        company_types: dict[str, int] = {}
        employee_buckets: dict[str, int] = {}

        for company in companies:
            ct = company.get("company_type", "unknown")
            eb = company.get("employee_count_bucket", "unknown")

            company_types[ct] = company_types.get(ct, 0) + 1
            employee_buckets[eb] = employee_buckets.get(eb, 0) + 1

        # Create aggregate for each company type
        for company_type, type_count in company_types.items():
            # Calculate type-specific adoption
            type_active = sum(
                1
                for c in companies
                if c.get("company_type") == company_type
                # Note: We don't have per-company pack data here,
                # so we use the overall adoption rate
            )
            type_adoption = (type_active / type_count * 100) if type_count > 0 else 0

            aggregate = PackUsageAggregate(
                date=aggregation_date,
                sector=sector,
                company_type=company_type,
                employee_bucket="all",  # Could be bucketed further if needed
                pack_id=pack_id,
                total_companies=type_count,
                active_companies=type_count,  # Simplified - all assumed active
                total_activations=cumulative,
                daily_activations=daily_activations,
                adoption_rate_pct=type_adoption,
                avg_usage_per_company=avg_usage,
                k_anonymity_met=total_companies >= K_ANONYMITY_THRESHOLD,
            )
            aggregates.append(aggregate)

    return aggregates


async def cleanup_old_aggregations(db: AsyncSession, retention_days: int = 730) -> int:  # 2 years
    """
    Remove aggregation data older than retention period.

    GDPR compliance: Data retention policy enforcement.

    Args:
        db: Database session
        retention_days: Number of days to retain data

    Returns:
        Number of records deleted
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

    result = await db.execute(
        select(PackUsageAggregate).where(PackUsageAggregate.date < cutoff_date)
    )
    old_records = result.scalars().all()

    deleted_count = len(old_records)

    for record in old_records:
        await db.delete(record)

    await db.commit()

    logger.info(f"Cleaned up {deleted_count} old aggregation records")
    return deleted_count


async def run_analytics_aggregation(
    aggregation_date: datetime | None = None,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Main entry point for analytics aggregation job.

    Aggregates pack usage data for benchmarking with privacy guarantees.

    Args:
        aggregation_date: Date to aggregate for (defaults to yesterday)

    Returns:
        Dictionary with aggregation results

    Example:
        >>> result = await run_analytics_aggregation()
        >>> print(f"Processed {result['sectors_processed']} sectors")
    """
    if aggregation_date is None:
        # Default to yesterday (we aggregate the previous day's data)
        aggregation_date = datetime.now(timezone.utc) - timedelta(days=1)

    # Normalize to midnight
    aggregation_date = aggregation_date.replace(hour=0, minute=0, second=0, microsecond=0)

    logger.info(f"Starting analytics aggregation for {aggregation_date.date()}")

    results: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "date": aggregation_date.isoformat(),
        "companies_total": 0,
        "companies_opted_out": 0,
        "sectors_found": 0,
        "sectors_k_anonymous": 0,
        "sectors_excluded": 0,
        "aggregates_created": 0,
        "errors": [],
    }

    async with get_db_session() as db:  # NOTE: get_db_session is asynccontextmanager at runtime
        try:
            # Step 1: Get all active companies
            companies = await get_active_companies(db)
            results["companies_total"] = len(companies)
            logger.info(f"Found {len(companies)} active companies")

            # Step 2: Get opted-out companies
            opted_out_ids = await get_opted_out_company_ids(db)
            results["companies_opted_out"] = len(opted_out_ids)
            logger.info(f"Found {len(opted_out_ids)} opted-out companies")

            # Step 3: Group by sector
            sector_groups = group_companies_by_sector(companies, opted_out_ids)
            results["sectors_found"] = len(sector_groups)
            logger.info(f"Found {len(sector_groups)} unique sectors")

            # Step 4: Filter to k-anonymous sectors
            k_anonymous_sectors = filter_k_anonymous_sectors(sector_groups)
            results["sectors_k_anonymous"] = len(k_anonymous_sectors)
            results["sectors_excluded"] = len(sector_groups) - len(k_anonymous_sectors)
            logger.info(
                f"{len(k_anonymous_sectors)} sectors meet k-anonymity, "
                f"{results['sectors_excluded']} excluded"
            )

            # Step 5: Aggregate data for each sector
            total_aggregates = 0

            if not SCHRIJF_PACK_USAGE_AGGREGATEN:
                logger.info("Analytics aggregation schrijft niets: %s", UITGESCHAKELD_REDEN)
                results["aggregation_disabled"] = UITGESCHAKELD_REDEN
                k_anonymous_sectors = {}

            for sector, sector_companies in k_anonymous_sectors.items():
                try:
                    aggregates = await aggregate_sector_data(
                        db, sector, sector_companies, aggregation_date, opted_out_ids
                    )

                    for aggregate in aggregates:
                        db.add(aggregate)

                    total_aggregates += len(aggregates)
                    logger.debug(f"Created {len(aggregates)} aggregates for {sector}")

                except Exception as e:
                    error_msg = f"Error aggregating sector {sector}: {e}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)

            await db.commit()
            results["aggregates_created"] = total_aggregates

            # Step 6: Cleanup old data
            deleted = await cleanup_old_aggregations(db)
            results["old_records_deleted"] = deleted

            logger.info(f"Analytics aggregation complete: {total_aggregates} aggregates created")

        except Exception as e:
            error_msg = f"Analytics aggregation failed: {e}"
            logger.error(error_msg, exc_info=True)
            results["errors"].append(error_msg)
            raise

    return results


# For running as script
if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        result = await run_analytics_aggregation()
        print(f"Aggregation results: {result}")

    asyncio.run(main())
