"""
Pack Health Aggregation Job

Background job that aggregates pack usage and calculates health status.
Runs daily to update pack metrics based on audit logs and error rates.
Includes pack deactivation logic for packs with critical health status.

Usage:
    from src.core.jobs.pack_health_job import update_pack_metrics
    await update_pack_metrics()

    # With deactivation processing
    from src.core.jobs.pack_health_job import update_pack_metrics_with_lifecycle
    await update_pack_metrics_with_lifecycle()
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.session import get_db_session
from src.core.procedures.models import DomainPack

logger = logging.getLogger(__name__)

# Health status thresholds
HEALTH_THRESHOLDS = {
    "usage_warning_days": 60,  # No usage for 60 days -> "warning"
    "usage_critical_days": 90,  # No usage for 90 days -> "critical"
    "error_rate_warning": 0.05,  # Error rate > 5% -> "warning"
    "error_rate_critical": 0.10,  # Error rate > 10% -> "critical"
}


async def aggregate_pack_usage(
    db: AsyncSession,
    since: datetime | None = None,
    tenant_id: int | None = None,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Aggregate usage from audit logs for the last 24 hours.

    Args:
        db: Database session
        since: Optional datetime to query from (defaults to 24h ago)

    Returns:
        Dictionary mapping pack_id to usage count
    """
    from src.core.procedures.models import PackActivationAuditLog

    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Query audit logs for pack usage in last 24h
    stmt = (
        select(
            PackActivationAuditLog.pack_id,
            func.count(PackActivationAuditLog.id).label("usage_count"),
        )
        .where(PackActivationAuditLog.created_at >= since)
    )
    if tenant_id is not None:
        stmt = stmt.where(PackActivationAuditLog.tenant_id == tenant_id)
    stmt = stmt.group_by(PackActivationAuditLog.pack_id)

    result = await db.execute(stmt)
    usage_counts = {row.pack_id: row.usage_count for row in result.all()}

    logger.info(
        "Aggregated usage for %d packs since %s", len(usage_counts), since
    )
    return usage_counts


async def calculate_pack_health(
    db: AsyncSession, tenant_id: int | None = None
) -> None:
    """
    Calculate health status for all packs based on usage and errors.

    Health logic:
    - No usage for 60 days -> "warning"
    - No usage for 90 days -> "critical"
    - Error rate > 5% -> "warning"
    - Error rate > 10% -> "critical"
    - Otherwise -> "healthy"

    Args:
        db: Database session
    """
    now = datetime.now(timezone.utc)
    warning_threshold = now - timedelta(days=HEALTH_THRESHOLDS["usage_warning_days"])
    critical_threshold = now - timedelta(days=HEALTH_THRESHOLDS["usage_critical_days"])

    # Get packs (optionally filtered by tenant)
    stmt = select(DomainPack)
    if tenant_id is not None:
        stmt = stmt.where(DomainPack.tenant_id == tenant_id)
    result = await db.execute(stmt)
    packs = result.scalars().all()

    updated_count = 0
    for pack in packs:
        new_health_status = "healthy"
        health_reasons = []

        # Check usage-based health
        last_used = pack.last_used_at
        if last_used:
            if last_used < critical_threshold:
                new_health_status = "critical"
                health_reasons.append(f"No usage for {(now - last_used).days} days")
            elif last_used < warning_threshold:
                new_health_status = "warning"
                health_reasons.append(f"No usage for {(now - last_used).days} days")

        # Check error rate-based health
        if pack.usage_count > 0:
            error_rate = pack.error_count / max(pack.usage_count, 1)
            if error_rate > HEALTH_THRESHOLDS["error_rate_critical"]:
                new_health_status = "critical"
                health_reasons.append(f"Error rate {error_rate:.1%}")
            elif error_rate > HEALTH_THRESHOLDS["error_rate_warning"]:
                if new_health_status != "critical":
                    new_health_status = "warning"
                health_reasons.append(f"Error rate {error_rate:.1%}")

        # Update pack if health status changed
        if pack.health_status != new_health_status:
            logger.info(
                "Pack %s (ID: %s) health changed: %s -> %s. Reasons: %s",
                pack.name,
                pack.id,
                pack.health_status,
                new_health_status,
                ", ".join(health_reasons),
            )
            pack.health_status = new_health_status
            updated_count += 1

        # Always update last_health_check
        pack.last_health_check = now

    await db.commit()
    logger.info(
        "Health check completed for %d packs, %d status updates",
        len(packs),
        updated_count,
    )


async def update_pack_usage_counts(
    db: AsyncSession, tenant_id: int | None = None
) -> None:
    """
    Update usage counts for packs based on recent audit log activity.

    Args:
        db: Database session
    """

    # Get usage counts from last 24h
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    usage_counts = await aggregate_pack_usage(db, since, tenant_id=tenant_id)

    # Update packs with new usage
    updated_count = 0
    for pack_id_str, count in usage_counts.items():
        try:
            pack_id = UUID(pack_id_str)
            stmt = select(DomainPack).where(DomainPack.id == pack_id)
            if tenant_id is not None:
                stmt = stmt.where(DomainPack.tenant_id == tenant_id)
            result = await db.execute(stmt)
            pack = result.scalar_one_or_none()

            if pack:
                pack.usage_count += count
                pack.last_used_at = datetime.now(timezone.utc)
                updated_count += 1
                logger.debug(
                    "Updated pack %s usage: +%d (total: %d)",
                    pack.name,
                    count,
                    pack.usage_count,
                )
        except (ValueError, TypeError) as e:
            logger.warning(
                "Invalid pack_id in audit logs: %s - %s", pack_id_str, e
            )

    await db.commit()
    logger.info("Updated usage counts for %d packs", updated_count)


async def process_pack_deactivations() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Process pack deactivations for packs with critical health status.

    This function handles the lifecycle management of packs:
    - Deactivates packs that have been critical beyond grace period
    - Sends notifications for warning and deactivated packs
    - Respects the auto-deactivation configuration setting

    Returns:
        Dictionary with deactivation results containing:
        - deactivated_count: Number of packs deactivated
        - warning_count: Number of warning packs processed
        - notification_count: Total notifications sent
        - errors: List of any errors encountered
    """
    from src.core.services.pack_lifecycle_service import pack_lifecycle_service

    logger.info("Starting pack deactivation processing")

    try:
        result = await pack_lifecycle_service.process_deactivations()
        logger.info(
            "Pack deactivation processing completed: %d deactivated, %d warnings",
            result.get("deactivated_count", 0),
            result.get("warning_count", 0),
        )
        return result
    except Exception as e:
        logger.error(
            "Pack deactivation processing failed: %s", e, exc_info=True
        )
        return {
            "deactivated_count": 0,
            "warning_count": 0,
            "notification_count": 0,
            "errors": [str(e)],
        }


async def update_pack_metrics(tenant_id: int | None = None) -> None:
    """
    Update all pack metrics.

    Main entry point for the pack health aggregation job.
    This function:
    1. Aggregates usage from audit logs
    2. Updates pack usage counts
    3. Calculates health status for all packs

    Should be called daily by the scheduler.
    """
    logger.info("Starting pack health metrics update")

    async with get_db_session() as db:
        try:
            # Step 1: Aggregate and update usage counts
            await update_pack_usage_counts(db, tenant_id=tenant_id)

            # Step 2: Calculate health status
            await calculate_pack_health(db, tenant_id=tenant_id)

            logger.info("Pack health metrics update completed successfully")
        except Exception as e:
            logger.error(
                "Pack health metrics update failed: %s", e, exc_info=True
            )
            raise


async def update_pack_metrics_with_lifecycle() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Update pack metrics and process lifecycle operations.

    Extended entry point that performs both health metrics update
    and lifecycle management (deactivations and notifications).

    This function:
    1. Aggregates usage from audit logs
    2. Updates pack usage counts
    3. Calculates health status for all packs
    4. Processes deactivations for critical packs
    5. Sends notifications for warning/critical packs

    Should be called daily by the scheduler for complete lifecycle management.

    Returns:
        Dictionary with combined metrics update and lifecycle results
    """
    logger.info("Starting pack metrics update with lifecycle processing")

    results = {
        "metrics_updated": False,
        "lifecycle": {},
    }

    try:
        # Step 1-3: Update metrics
        await update_pack_metrics()
        results["metrics_updated"] = True

        # Step 4-5: Process lifecycle
        lifecycle_results = await process_pack_deactivations()
        results["lifecycle"] = lifecycle_results

        logger.info("Pack metrics update with lifecycle completed successfully")

    except Exception as e:
        logger.error(
            "Pack metrics update with lifecycle failed: %s", e, exc_info=True
        )
        results["error"] = str(e)

    return results
