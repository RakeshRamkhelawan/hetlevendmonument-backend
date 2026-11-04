"""Profile Aggregator -- transforms UserBehaviorObservation into UserCognitiveProfile.

Usage:
    aggregator = ProfileAggregator(db)
    profile = await aggregator.aggregate(tenant_id=1, human_user_id="abc")
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.batching.batch_manager import PendingObservation
from src.core.learning.twin_models import UserBehaviorObservation, UserCognitiveProfile

# Mapping from behavior_type to optimal_help_style
_HELP_STYLE_MAP: dict[str, str] = {
    "file_edit": "direct_code",
    "rapid_switch": "step_by_step",
    "undo_loop": "explain_first",
    "focus_builder.workflow_accepted": "direct_code",
    "focus_builder.ai_generate": "concise",
    "focus_builder.flow_executed": "direct_code",
    "focus_builder.flow_created": "direct_code",
    "default": "direct_code",
}

# Time buckets for work_patterns histogram
_TIME_BUCKETS = [
    ("morning", 6, 12),
    ("afternoon", 12, 18),
    ("evening", 18, 24),
    ("night", 0, 6),
]


class ProfileAggregator:
    """Aggregate observations into a cognitive profile."""

    def __init__(
        self,
        db: AsyncSession,
        consent_manager: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self._db = db
        self._consent = consent_manager

    async def aggregate(
        self,
        tenant_id: int,
        human_user_id: str,
    ) -> UserCognitiveProfile | None:
        """Aggregate observations for a single user into their cognitive profile.

        Uses incremental aggregation via the ``last_aggregated_at`` watermark.
        If no profile exists yet, one is created from scratch.

        Returns:
            The updated (or created) profile, or None if no observations exist
            or profile_aggregation consent is disabled.
        """
        # 0. Check profile_aggregation consent (ADR-026 S.2)
        if self._consent is not None:
            try:
                categories = await self._consent.get_consent_categories(
                    human_user_id, tenant_id
                )
                if not categories.profile_aggregation:
                    logger.debug(
                        "twin_profile_aggregation_blocked_by_consent",
                        tenant_id=tenant_id,
                        human_user_id=human_user_id,
                    )
                    return None
            except Exception as exc:
                # Fail-safe: if consent check fails, proceed with aggregation
                # (blocking the user is worse than accidentally aggregating)
                logger.warning(
                    "twin_profile_consent_check_failed",
                    tenant_id=tenant_id,
                    human_user_id=human_user_id,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

        # 1. Load existing profile (if any)
        profile = await self._get_profile(tenant_id, human_user_id)
        watermark = profile.last_aggregated_at if profile else None

        # 2. Fetch observations newer than watermark
        observations = await self._fetch_observations(tenant_id, human_user_id, watermark)
        if not observations:
            logger.debug(
                "twin_aggregate_no_new_observations",
                tenant_id=tenant_id,
                human_user_id=human_user_id,
            )
            return profile

        # 3. Compute stats from new observations
        new_stats = self._compute_stats(observations)

        # 4. Merge with existing profile or create new
        if profile:
            merged = self._merge_profiles(profile, new_stats)
        else:
            merged = self._create_profile(tenant_id, human_user_id, new_stats)

        # 5. Upsert
        merged.last_aggregated_at = datetime.now(timezone.utc)
        await self._upsert_profile(merged)

        logger.info(
            "twin_profile_aggregated",
            tenant_id=tenant_id,
            human_user_id=human_user_id,
            observation_count=len(observations),
            profile_confidence=merged.confidence_level,
        )
        return merged

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_profile(self, tenant_id: int, human_user_id: str) -> UserCognitiveProfile | None:
        result = await self._db.execute(
            select(UserCognitiveProfile).where(
                UserCognitiveProfile.tenant_id == tenant_id,
                UserCognitiveProfile.human_user_id == human_user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _fetch_observations(
        self,
        tenant_id: int,
        human_user_id: str,
        watermark: datetime | None,
    ) -> list[UserBehaviorObservation]:
        stmt = (
            select(UserBehaviorObservation)
            .where(
                UserBehaviorObservation.tenant_id == tenant_id,
                UserBehaviorObservation.human_user_id == human_user_id,
            )
            .order_by(UserBehaviorObservation.created_at.asc())
        )
        if watermark is not None:
            stmt = stmt.where(UserBehaviorObservation.created_at > watermark)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    def _compute_stats(self, observations: list[UserBehaviorObservation]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Compute aggregation statistics from a batch of observations."""
        count = len(observations)

        # Confidence level -- average of confidence_score
        confidence_sum = sum(obs.confidence_score for obs in observations)
        confidence_avg = confidence_sum / count if count else 0.0

        # Behavior type frequency (for help style mapping)
        behavior_counts: Counter[str] = Counter()
        for obs in observations:
            behavior_counts[obs.behavior_type] += 1

        # Time distribution for work_patterns
        time_buckets: Counter[str] = Counter()
        for obs in observations:
            if obs.created_at is None:
                continue
            hour = obs.created_at.hour
            for label, start, end in _TIME_BUCKETS:
                if start <= hour < end:
                    time_buckets[label] += 1
                    break

        # Coding style -- merge context fields
        coding_style_counter: Counter[str] = Counter()
        for obs in observations:
            ctx = obs.context or {}
            for key, value in ctx.items():
                if isinstance(value, bool) and value:
                    coding_style_counter[key] += 1

        # Outcome metrics -- track success/failure per behavior_type
        success_counts: Counter[str] = Counter()
        failure_counts: Counter[str] = Counter()
        for obs in observations:
            metrics = obs.outcome_metrics or {}
            success = metrics.get("success", False)
            success_rate = metrics.get("success_rate", 1.0 if success else 0.0)
            if success_rate >= 0.8:
                success_counts[obs.behavior_type] += 1
            elif success_rate < 0.5:
                failure_counts[obs.behavior_type] += 1

        # Preferred agents / departments from Focus Builder context
        preferred_agents_counter: Counter[str] = Counter()
        preferred_departments_counter: Counter[str] = Counter()
        for obs in observations:
            ctx = obs.context or {}
            agent_ids = ctx.get("preferred_agent_ids", [])
            if isinstance(agent_ids, list):
                for aid in agent_ids:
                    preferred_agents_counter[str(aid)] += 1
            dept = ctx.get("department")
            if dept:
                preferred_departments_counter[str(dept)] += 1

        return {
            "count": count,
            "confidence_avg": confidence_avg,
            "behavior_counts": behavior_counts,
            "time_buckets": time_buckets,
            "coding_style_counter": coding_style_counter,
            "success_counts": success_counts,
            "failure_counts": failure_counts,
            "preferred_agents_counter": preferred_agents_counter,
            "preferred_departments_counter": preferred_departments_counter,
        }

    def _merge_profiles(
        self,
        existing: UserCognitiveProfile,
        new_stats: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> UserCognitiveProfile:
        """Merge new stats into an existing profile."""
        old_count = existing.observation_count
        new_count = new_stats["count"]
        total_count = old_count + new_count

        # observation_count
        existing.observation_count = total_count

        # confidence_level -- EWMA(alpha=0.3): 70% old, 30% new
        if total_count > 0:
            existing.confidence_level = (
                existing.confidence_level * 0.7 + new_stats["confidence_avg"] * 0.3
            )
            existing.confidence_level = min(1.0, max(0.0, existing.confidence_level))

        # optimal_help_style -- weighted by observation count
        existing.optimal_help_style = self._resolve_help_style(
            existing.optimal_help_style,
            existing.observation_count - new_count,  # old weight
            new_stats["behavior_counts"],
        )

        # work_patterns -- update histogram
        existing.work_patterns = self._merge_work_patterns(
            existing.work_patterns or {},
            new_stats["time_buckets"],
            total_count,
        )

        # coding_style -- merge frequency maps
        existing.coding_style = self._merge_coding_style(
            existing.coding_style or {},
            new_stats["coding_style_counter"],
            total_count,
        )

        # strengths / blind_spots -- top-3 by frequency
        existing.strengths = self._resolve_top3(
            existing.strengths or [],
            new_stats["success_counts"],
        )
        existing.blind_spots = self._resolve_top3(
            existing.blind_spots or [],
            new_stats["failure_counts"],
        )

        # preferred_agents / preferred_departments
        existing.preferred_agents = self._merge_frequency_list(
            existing.preferred_agents or [],
            new_stats["preferred_agents_counter"],
        )
        existing.preferred_departments = self._merge_frequency_list(
            existing.preferred_departments or [],
            new_stats["preferred_departments_counter"],
        )

        return existing

    def _create_profile(
        self,
        tenant_id: int,
        human_user_id: str,
        stats: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> UserCognitiveProfile:
        """Create a brand-new profile from observation stats."""
        count = stats["count"]

        work_patterns = self._merge_work_patterns({}, stats["time_buckets"], count)
        coding_style = self._merge_coding_style({}, stats["coding_style_counter"], count)

        return UserCognitiveProfile(
            tenant_id=tenant_id,
            human_user_id=human_user_id,
            observation_count=count,
            confidence_level=min(1.0, max(0.0, stats["confidence_avg"])),
            optimal_help_style=self._resolve_help_style(None, 0, stats["behavior_counts"]),
            work_patterns=work_patterns,
            coding_style=coding_style,
            strengths=self._resolve_top3([], stats["success_counts"]),
            blind_spots=self._resolve_top3([], stats["failure_counts"]),
            preferred_agents=self._merge_frequency_list([], stats["preferred_agents_counter"]),
            preferred_departments=self._merge_frequency_list(
                [], stats["preferred_departments_counter"]
            ),
        )

    # ------------------------------------------------------------------
    # Merge helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_help_style(
        current_style: str | None,
        current_weight: int,
        behavior_counts: Counter[str],
    ) -> str:
        """Pick the most frequent behavior type and map to help style."""
        # Weighted vote: existing style gets weight = current_weight
        votes: Counter[str] = Counter()
        if current_style and current_weight > 0:
            votes[current_style] = current_weight

        for behavior, count in behavior_counts.items():
            style = _HELP_STYLE_MAP.get(behavior, _HELP_STYLE_MAP["default"])
            votes[style] += count

        if not votes:
            return _HELP_STYLE_MAP["default"]

        return votes.most_common(1)[0][0]

    @staticmethod
    def _merge_work_patterns(
        existing: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        new_buckets: Counter[str],
        total_count: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Merge time-bucket histograms and normalize to percentages."""
        merged = Counter(existing.get("time_distribution", {}))
        merged.update(new_buckets)

        if total_count == 0:
            return {"time_distribution": {}}

        return {
            "time_distribution": {
                label: round(merged[label] / total_count, 3) for label, _, _ in _TIME_BUCKETS
            }
        }

    @staticmethod
    def _merge_coding_style(
        existing: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        new_counter: Counter[str],
        total_count: int,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Merge coding-style boolean frequencies."""
        merged = Counter(existing)
        merged.update(new_counter)

        if total_count == 0:
            return {}

        return {key: round(merged[key] / total_count, 3) for key in sorted(merged.keys())}

    @staticmethod
    def _resolve_top3(
        existing: list[Any],  # TODO(TYPE): replace Any with concrete type
        new_counter: Counter[str],
    ) -> list[str]:
        """Return top-3 most frequent items."""
        merged: Counter[str] = Counter()
        # Decay existing entries slightly (0.9 weight)
        for item in existing:
            merged[str(item)] = 1  # weight decay approximation
        merged.update(new_counter)
        return [item for item, _ in merged.most_common(3)]

    @staticmethod
    def _merge_frequency_list(
        existing: list[Any],  # TODO(TYPE): replace Any with concrete type
        new_counter: Counter[str],
    ) -> list[str]:
        """Merge frequency lists and return sorted by frequency."""
        merged: Counter[str] = Counter()
        for item in existing:
            merged[str(item)] += 1
        merged.update(new_counter)
        return [item for item, _ in merged.most_common()]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _upsert_profile(self, profile: UserCognitiveProfile) -> None:
        """Upsert profile using PostgreSQL ON CONFLICT.

        UserCognitiveProfile has a UNIQUE index on
        (tenant_id, human_user_id).
        """
        data = {
            "tenant_id": profile.tenant_id,
            "human_user_id": profile.human_user_id,
            "coding_style": profile.coding_style,
            "work_patterns": profile.work_patterns,
            "blind_spots": profile.blind_spots,
            "strengths": profile.strengths,
            "optimal_help_style": profile.optimal_help_style,
            "confidence_level": profile.confidence_level,
            "observation_count": profile.observation_count,
            "preferred_agents": profile.preferred_agents,
            "preferred_departments": profile.preferred_departments,
            "last_aggregated_at": profile.last_aggregated_at,
        }

        stmt = pg_insert(UserCognitiveProfile).values(**data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["tenant_id", "human_user_id"],
            set_={k: v for k, v in data.items() if k not in ("tenant_id", "human_user_id")},
        )
        await self._db.execute(stmt)
