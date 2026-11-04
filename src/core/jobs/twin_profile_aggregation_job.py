"""Digital Twin Profile Aggregation Job.

Background job that aggregates UserBehaviorObservation rows into
UserCognitiveProfile entries. Runs daily via Dramatiq.

Usage:
    from src.core.jobs.twin_profile_aggregation_job import aggregate_all_profiles
    result = await aggregate_all_profiles()
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.bypass_session import adopt_tenant
from src.core.database.session import get_db_session
from src.core.learning.metrics import record_twin_aggregation_users_processed
from src.core.learning.services.profile_aggregator import ProfileAggregator
from src.core.learning.twin_models import UserBehaviorObservation
from src.core.models.rbac_models import Tenant
from src.core.utils.best_effort import best_effort


async def aggregate_all_profiles(
    batch_size: int = 100,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Aggregate profiles for all users with new observations.

    Processes users in paginated batches to avoid memory pressure.
    Per-user failures are logged but do NOT stop the batch.

    Args:
        batch_size: Number of distinct users to process per query.

    Returns:
        Dict with job statistics.
    """
    start_time = datetime.now(timezone.utc)
    stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "processed": 0,
        "failed": 0,
        "skipped": 0,
        "start_time": start_time.isoformat(),
    }
    tenant_processed_counts: dict[int, int] = {}

    async with get_db_session() as db:
        # BUITEN naar BINNEN: eerst de klanten, dan per klant de gebruikers (OP-153).
        #
        # Deze lus liep tot 2026-09-16 andersom: een enkele `SELECT DISTINCT tenant_id,
        # human_user_id` over ALLE observaties, en daarna per rij het werk. Dat leunt op
        # het feit dat de applicatie als tabeleigenaar verbindt, want `user_behavior_
        # observations` heeft een afschermingsregel. Gemeten 2026-09-16 op de keten-
        # database, als de niet-eigenaar `ss_app2` en zonder klantcontext:
        #
        #     SELECT count(*) FROM user_behavior_observations  ->  0
        #     SELECT count(*) FROM tenants                     ->  2
        #
        # Deze nachtelijke taak zou dus nul gebruikers vinden en "succesvol" eindigen --
        # geen foutmelding, geen enkel signaal. `tenants` heeft GEEN afschermingsregel
        # (gemeten: `relrowsecurity = f`, nul policies) en `sanskritisetu_app` heeft er
        # SELECT op, en dat is precies wat deze opbouw nodig heeft: de klantenlijst is
        # de enige lezing die klant-overstijgend hoeft te zijn.
        tenant_ids = [rij[0] for rij in (await db.execute(select(Tenant.id))).all()]

        for tenant_id in tenant_ids:
            # `tenant_id` komt uit de database, nooit uit invoer.
            async with adopt_tenant(db, tenant_id):
                offset = 0
                while True:
                    gebruikers = await _fetch_user_batch(db, tenant_id, batch_size, offset)
                    if not gebruikers:
                        break

                    for human_user_id in gebruikers:
                        success = False
                        async with best_effort(
                            "twin_profile_aggregation",
                            db_session=db,
                        ):
                            aggregator = ProfileAggregator(db)
                            profile = await aggregator.aggregate(
                                tenant_id=tenant_id,
                                human_user_id=human_user_id,
                            )
                            success = True
                            if profile:
                                stats["processed"] += 1
                                tenant_processed_counts[tenant_id] = (
                                    tenant_processed_counts.get(tenant_id, 0) + 1
                                )
                            else:
                                stats["skipped"] += 1
                        if not success:
                            stats["failed"] += 1

                    offset += batch_size
                    logger.debug(
                        "twin_aggregate_batch_complete",
                        tenant_id=tenant_id,
                        batch_size=len(gebruikers),
                        offset=offset,
                        processed=stats["processed"],
                        failed=stats["failed"],
                    )

    end_time = datetime.now(timezone.utc)
    stats["end_time"] = end_time.isoformat()
    stats["duration_seconds"] = (end_time - start_time).total_seconds()

    # Record per-tenant metrics
    for tid, count in tenant_processed_counts.items():
        record_twin_aggregation_users_processed(tid, count)

    logger.info(
        "twin_profile_aggregation_complete",
        processed=stats["processed"],
        failed=stats["failed"],
        skipped=stats["skipped"],
        duration_seconds=stats["duration_seconds"],
    )
    return stats


async def _fetch_user_batch(
    db: AsyncSession,
    tenant_id: int,
    limit: int,
    offset: int,
) -> list[str]:
    """Geef een pagina distinct `human_user_id` van EEN klant terug.

    De `tenant_id`-filter staat er expliciet bij en niet alleen als aangenomen context.
    Dat is bewust dubbelop: de afschermingsregel dekt dit al zodra de applicatie als
    `sanskritisetu_app` verbindt, maar vandaag verbindt zij nog als tabeleigenaar en
    slaat PostgreSQL de regel over. Zonder deze WHERE zou de lus in de tussentijd per
    klant ALLE gebruikers verwerken.
    """
    stmt = (
        select(UserBehaviorObservation.human_user_id)
        .where(UserBehaviorObservation.tenant_id == tenant_id)
        .distinct()
        .order_by(UserBehaviorObservation.human_user_id)
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    return [row[0] for row in result.all()]
