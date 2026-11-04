"""
TenantAdminStats -- aggregate Digital Twin stats for the admin dashboard.

All queries are scoped to a single tenant_id.  system_admin callers may
pass any tenant_id; regular admins are restricted to their own tenant by
the endpoint layer.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.twin_models import (
    UserBehaviorObservation,
    UserCognitiveProfile,
    UserTwinConsent,
)


async def get_twin_stats(
    db: AsyncSession,
    tenant_id: int,
    active_window_days: int = 30,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Return aggregated Digital Twin stats for *tenant_id*.

    Args:
        db:                 Async DB session (RLS must be set by the caller).
        tenant_id:          Target tenant.
        active_window_days: Window for "active users" definition (default 30d).

    Returns:
        Dict with observation_total, active_users, profile_count,
        consent_breakdown, hard_delete_pending.
    """
    since = datetime.now(timezone.utc) - timedelta(days=active_window_days)

    # -- Total observations ----------------------------------------------------
    obs_total_result = await db.execute(
        select(func.count())
        .select_from(UserBehaviorObservation)
        .where(UserBehaviorObservation.tenant_id == tenant_id)
    )
    observation_total: int = obs_total_result.scalar_one() or 0

    # -- Active users (distinct hashed IDs in the window) ---------------------
    active_users_result = await db.execute(
        select(func.count(func.distinct(UserBehaviorObservation.human_user_id)))
        .select_from(UserBehaviorObservation)
        .where(
            UserBehaviorObservation.tenant_id == tenant_id,
            UserBehaviorObservation.created_at >= since,
        )
    )
    active_users: int = active_users_result.scalar_one() or 0

    # -- Cognitive profiles ----------------------------------------------------
    profile_count_result = await db.execute(
        select(func.count())
        .select_from(UserCognitiveProfile)
        .where(UserCognitiveProfile.tenant_id == tenant_id)
    )
    profile_count: int = profile_count_result.scalar_one() or 0

    # -- Consent breakdown -----------------------------------------------------
    consent_result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(func.cast(UserTwinConsent.behavior_tracking, Integer)).label(
                "behavior_tracking_on"
            ),
            func.sum(func.cast(UserTwinConsent.profile_aggregation, Integer)).label(
                "profile_aggregation_on"
            ),
            func.sum(func.cast(UserTwinConsent.ai_interventions, Integer)).label(
                "ai_interventions_on"
            ),
            func.sum(func.cast(UserTwinConsent.cross_session_memory, Integer)).label(
                "cross_session_memory_on"
            ),
            func.sum(func.cast(UserTwinConsent.hard_delete_requested, Integer)).label(
                "hard_delete_pending"
            ),
        ).where(UserTwinConsent.tenant_id == tenant_id)
    )
    consent_row = consent_result.mappings().one_or_none() or {}

    total_consents = int(consent_row.get("total") or 0)
    hard_delete_pending = int(consent_row.get("hard_delete_pending") or 0)

    consent_breakdown = {
        "total": total_consents,
        "behavior_tracking_on": int(consent_row.get("behavior_tracking_on") or 0),
        "profile_aggregation_on": int(consent_row.get("profile_aggregation_on") or 0),
        "ai_interventions_on": int(consent_row.get("ai_interventions_on") or 0),
        "cross_session_memory_on": int(consent_row.get("cross_session_memory_on") or 0),
    }

    return {
        "tenant_id": tenant_id,
        "observation_total": observation_total,
        "active_users_last_30d": active_users,
        "profile_count": profile_count,
        "consent_breakdown": consent_breakdown,
        "hard_delete_pending": hard_delete_pending,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
