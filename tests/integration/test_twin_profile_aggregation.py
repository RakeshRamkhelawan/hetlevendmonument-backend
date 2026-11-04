"""Integration tests for Digital Twin profile aggregation.

Tests verify that ProfileAggregator correctly transforms observations
into cognitive profiles, with full tenant isolation and idempotency.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.services.profile_aggregator import ProfileAggregator
from src.core.learning.twin_models import (
    UserBehaviorObservation,
    UserCognitiveProfile,
)
from src.core.models.rbac_models import Tenant


async def _ensure_tenant(db: AsyncSession, tenant_id: int) -> None:
    """Create a test tenant if it does not exist."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if result.scalar_one_or_none() is None:
        tenant = Tenant(
            id=tenant_id,
            name=f"Test Tenant {tenant_id}",
            slug=f"test-{tenant_id}",
            is_active=True,
            max_users=100,
        )
        db.add(tenant)
        await db.commit()


async def _insert_observations(
    db: AsyncSession,
    tenant_id: int,
    human_user_id: str,
    count: int,
    behavior_type: str = "file_edit",
    confidence_score: float = 1.0,
    context: dict | None = None,
    outcome_metrics: dict | None = None,
) -> None:
    """Helper to insert test observations."""
    base_time = datetime.now(timezone.utc) - timedelta(hours=count)
    for i in range(count):
        obs = UserBehaviorObservation(
            tenant_id=tenant_id,
            human_user_id=human_user_id,
            session_id=f"sess_{i}",
            behavior_type=behavior_type,
            context=context or {"edit_count": i},
            outcome_metrics=outcome_metrics or {"success_rate": 0.9},
            confidence_score=confidence_score,
            created_at=base_time + timedelta(minutes=i),
            expires_at=base_time + timedelta(minutes=i, days=90),
        )
        db.add(obs)
    await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_aggregate_profile_from_observations(
    db_session: AsyncSession,
) -> None:
    """50 observations → correct profile with all fields populated."""
    tenant_id = 42
    user_id = "user_abc"

    await _ensure_tenant(db_session, tenant_id)
    await _insert_observations(
        db=db_session,
        tenant_id=tenant_id,
        human_user_id=user_id,
        count=50,
        behavior_type="file_edit",
        confidence_score=0.8,
    )

    aggregator = ProfileAggregator(db_session)
    profile = await aggregator.aggregate(tenant_id=tenant_id, human_user_id=user_id)

    assert profile is not None
    assert profile.observation_count == 50
    assert 0.0 <= profile.confidence_level <= 1.0
    assert profile.optimal_help_style == "direct_code"  # file_edit maps to this
    assert profile.last_aggregated_at is not None

    # Verify work_patterns has time distribution
    assert profile.work_patterns is not None
    assert "time_distribution" in profile.work_patterns


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_aggregate_is_idempotent(
    db_session: AsyncSession,
) -> None:
    """Running aggregation twice with same observations yields identical profile."""
    tenant_id = 43
    user_id = "user_idem"

    await _ensure_tenant(db_session, tenant_id)
    await _insert_observations(
        db=db_session,
        tenant_id=tenant_id,
        human_user_id=user_id,
        count=10,
        behavior_type="undo_loop",
        confidence_score=0.6,
    )

    aggregator = ProfileAggregator(db_session)
    profile1 = await aggregator.aggregate(tenant_id=tenant_id, human_user_id=user_id)
    first_watermark = profile1.last_aggregated_at

    # Second run — watermark should exclude already-processed observations
    profile2 = await aggregator.aggregate(tenant_id=tenant_id, human_user_id=user_id)

    assert profile2 is not None
    assert profile2.observation_count == profile1.observation_count
    assert profile2.confidence_level == pytest.approx(profile1.confidence_level)
    assert profile2.last_aggregated_at >= first_watermark


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_aggregate_respects_tenant_isolation(
    db_session: AsyncSession,
) -> None:
    """Tenant 1 aggregation must NOT create/update profiles for tenant 2."""
    await _ensure_tenant(db_session, 100)
    await _ensure_tenant(db_session, 200)
    await _insert_observations(
        db=db_session,
        tenant_id=100,
        human_user_id="user_t1",
        count=5,
    )
    await _insert_observations(
        db=db_session,
        tenant_id=200,
        human_user_id="user_t2",
        count=5,
    )

    aggregator = ProfileAggregator(db_session)
    await aggregator.aggregate(tenant_id=100, human_user_id="user_t1")

    # Tenant 2 profile should NOT exist
    result = await db_session.execute(
        select(func.count())
        .select_from(UserCognitiveProfile)
        .where(
            UserCognitiveProfile.tenant_id == 200,
            UserCognitiveProfile.human_user_id == "user_t2",
        )
    )
    assert result.scalar() == 0


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_aggregate_multiple_behavior_types(
    db_session: AsyncSession,
) -> None:
    """Mixed behavior types produce correct help style and strengths/blind_spots."""
    tenant_id = 44
    user_id = "user_mixed"

    await _ensure_tenant(db_session, tenant_id)
    # 30 file_edit (success)
    await _insert_observations(
        db=db_session,
        tenant_id=tenant_id,
        human_user_id=user_id,
        count=30,
        behavior_type="file_edit",
        outcome_metrics={"success_rate": 0.95},
    )
    # 10 undo_loop (failure)
    await _insert_observations(
        db=db_session,
        tenant_id=tenant_id,
        human_user_id=user_id,
        count=10,
        behavior_type="undo_loop",
        outcome_metrics={"success_rate": 0.2},
    )

    aggregator = ProfileAggregator(db_session)
    profile = await aggregator.aggregate(tenant_id=tenant_id, human_user_id=user_id)

    assert profile is not None
    assert profile.observation_count == 40
    # file_edit is most frequent → direct_code
    assert profile.optimal_help_style == "direct_code"
    # strengths should include file_edit (high success)
    assert "file_edit" in profile.strengths
    # blind_spots should include undo_loop (low success)
    assert "undo_loop" in profile.blind_spots


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_postgres
async def test_upsert_does_not_duplicate_profiles(
    db_session: AsyncSession,
) -> None:
    """Running aggregation on existing profile must not create duplicate rows."""
    tenant_id = 45
    user_id = "user_upsert"

    await _ensure_tenant(db_session, tenant_id)
    # Pre-create a profile
    profile = UserCognitiveProfile(
        tenant_id=tenant_id,
        human_user_id=user_id,
        observation_count=5,
        confidence_level=0.5,
    )
    db_session.add(profile)
    await db_session.commit()

    # Insert new observations
    await _insert_observations(
        db=db_session,
        tenant_id=tenant_id,
        human_user_id=user_id,
        count=10,
    )

    # Aggregate
    aggregator = ProfileAggregator(db_session)
    await aggregator.aggregate(tenant_id=tenant_id, human_user_id=user_id)

    # Verify exactly 1 row
    result = await db_session.execute(
        select(func.count())
        .select_from(UserCognitiveProfile)
        .where(
            UserCognitiveProfile.tenant_id == tenant_id,
            UserCognitiveProfile.human_user_id == user_id,
        )
    )
    assert result.scalar() == 1

    # Verify count was updated (5 + 10 = 15)
    result2 = await db_session.execute(
        select(UserCognitiveProfile.observation_count).where(
            UserCognitiveProfile.tenant_id == tenant_id,
            UserCognitiveProfile.human_user_id == user_id,
        )
    )
    assert result2.scalar() == 15
