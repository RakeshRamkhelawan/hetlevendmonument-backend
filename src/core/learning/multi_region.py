"""
Multi-region support for distributed learning.

Provides:
- Region-aware model loading
- Cross-region synchronization
- Regional preference learning
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, cast

import redis.asyncio as redis

logger = logging.getLogger(__name__)


@dataclass
class Region:
    """Represents a deployment region."""

    code: str  # e.g., "eu-west", "us-east", "ap-south"
    name: str
    timezone: str
    active: bool = True
    preferences: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        if self.preferences is None:
            self.preferences = {}


@dataclass
class RegionalInsight:
    """Insight tied to a specific region."""

    insight_id: str
    region_code: str
    category: str
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: datetime
    shared: bool = False


class RegionManager:
    """
    Manages multi-region configuration.
    """

    # Predefined regions
    REGIONS = {
        "eu-west": Region("eu-west", "Europe West", "Europe/Amsterdam"),
        "us-east": Region("us-east", "US East", "America/New_York"),
        "ap-south": Region("ap-south", "Asia Pacific South", "Asia/Kolkata"),
    }

    def __init__(self) -> None:
        self.current_region: str | None = None
        self._load_region_config()

    def _load_region_config(self) -> None:
        """Load current region from environment."""
        import os

        self.current_region = os.getenv("DEPLOYMENT_REGION", "eu-west")
        if self.current_region not in self.REGIONS:
            logger.warning(f"Unknown region: {self.current_region}, defaulting to eu-west")
            self.current_region = "eu-west"

    def get_current_region(self) -> Region:
        """Get current deployment region."""
        region_code = self.current_region or "eu-west"
        return self.REGIONS.get(region_code, self.REGIONS["eu-west"])

    def get_all_regions(self) -> list[Region]:
        """Get all active regions."""
        return [r for r in self.REGIONS.values() if r.active]

    def is_multi_region(self) -> bool:
        """Check if multi-region is enabled."""
        return len(self.get_all_regions()) > 1


class RegionalLearningStore:
    """
    Region-aware learning data storage.

    Stores insights locally but supports cross-region
    synchronization for shared patterns.
    """

    def __init__(
        self, redis_client: redis.Redis | None = None, tenant_id: int = 0  # type: ignore[type-arg]
    ) -> None:
        self.redis = redis_client
        self.tenant_id = tenant_id
        self.region = RegionManager().get_current_region()

    def _key(self, suffix: str) -> str:
        """Generate region-scoped key."""
        return f"learning:{self.tenant_id}:{self.region.code}:{suffix}"

    def _shared_key(self, suffix: str) -> str:
        """Generate shared (cross-region) key."""
        return f"learning:shared:{suffix}"

    async def store_regional_insight(
        self,
        insight_id: str,
        category: str,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        share_across_regions: bool = False,
    ) -> RegionalInsight:
        """
        Store an insight with region metadata.

        Args:
            insight_id: Unique insight ID
            category: Insight category
            data: Insight data
            share_across_regions: Whether to share with other regions
        """
        regional = RegionalInsight(
            insight_id=insight_id,
            region_code=self.region.code,
            category=category,
            data=data,
            created_at=datetime.now(timezone.utc),
            shared=share_across_regions,
        )

        # Store locally
        if self.redis:
            key = self._key(f"insights:{insight_id}")
            await self.redis.set(
                key,
                json.dumps(
                    {
                        "insight_id": regional.insight_id,
                        "category": regional.category,
                        "data": regional.data,
                        "created_at": regional.created_at.isoformat(),
                        "shared": regional.shared,
                    }
                ),
            )

            # If shared, also store in shared namespace
            if share_across_regions:
                shared_key = self._shared_key(f"insights:{insight_id}")
                raw_data = await self.redis.get(key)
                if raw_data is not None:
                    await self.redis.set(shared_key, raw_data)

        return regional

    async def get_regional_insights(
        self, category: str | None = None, include_shared: bool = True
    ) -> list[RegionalInsight]:
        """
        Get insights for current region.

        Args:
            category: Filter by category
            include_shared: Include shared insights from other regions
        """
        insights: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        if not self.redis:
            return insights

        # Get local insights
        pattern = self._key("insights:*")
        local_keys = await self.redis.keys(pattern)

        for key in local_keys:
            data = await self.redis.get(key)
            if data:
                parsed = json.loads(data)
                if category and parsed.get("category") != category:
                    continue
                insights.append(
                    RegionalInsight(
                        insight_id=parsed["insight_id"],
                        region_code=self.region.code,
                        category=parsed["category"],
                        data=parsed["data"],
                        created_at=datetime.fromisoformat(parsed["created_at"]),
                        shared=parsed.get("shared", False),
                    )
                )

        # Get shared insights from other regions
        if include_shared:
            shared_pattern = self._shared_key("insights:*")
            shared_keys = await self.redis.keys(shared_pattern)

            for key in shared_keys:
                # Skip if we already have this locally
                insight_id = key.split(":")[-1]
                if any(i.insight_id == insight_id for i in insights):
                    continue

                data = await self.redis.get(key)
                if data:
                    parsed = json.loads(data)
                    if category and parsed.get("category") != category:
                        continue
                    insights.append(
                        RegionalInsight(
                            insight_id=parsed["insight_id"],
                            region_code=parsed.get("region_code", "unknown"),
                            category=parsed["category"],
                            data=parsed["data"],
                            created_at=datetime.fromisoformat(parsed["created_at"]),
                            shared=True,
                        )
                    )

        return insights


class RegionalPreferenceLearner:
    """
    Learn preferences specific to a region.

    Examples:
    - Language preferences
    - Time-of-day patterns
    - Cultural conventions
    """

    def __init__(self, region: Region) -> None:
        self.region = region
        self.preferences: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

    def learn_language_preference(self, language_usage: dict[str, int]) -> str:
        """
        Learn preferred language from usage patterns.

        Args:
            language_usage: Dict[str, Any] of language -> usage count  # TODO(TYPE): replace Any with concrete type

        Returns:
            Preferred language code
        """
        if not language_usage:
            return "en"

        preferred = max(language_usage.items(), key=lambda x: x[1])[0]
        self.preferences["language"] = preferred

        return preferred

    def learn_time_pattern(
        self, activity_hours: list[int]
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Learn peak activity hours.

        Args:
            activity_hours: List[Any] of hours (0-23) when activity occurred  # TODO(TYPE): replace Any with concrete type

        Returns:
            Time pattern dict
        """
        from collections import Counter

        if not activity_hours:
            return {}

        hour_counts = Counter(activity_hours)
        peak_hours = [h for h, c in hour_counts.most_common(3)]

        pattern = {
            "peak_hours": peak_hours,
            "quiet_hours": [h for h in range(24) if h not in peak_hours][:6],
        }

        self.preferences["time_pattern"] = pattern

        return pattern

    def get_regional_context(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get context adapted to region.

        Returns:
            Regional context dict for prompts
        """
        return {
            "region": self.region.name,
            "timezone": self.region.timezone,
            "language": self.preferences.get("language", "en"),
            "time_pattern": self.preferences.get("time_pattern", {}),
        }


class CrossRegionSync:
    """
    Synchronize learning data across regions.
    """

    def __init__(self, redis_client: redis.Redis | None = None) -> None:  # type: ignore[type-arg]
        self.redis: redis.Redis | None = redis_client  # type: ignore[type-arg]
        self.region = RegionManager().get_current_region()

    async def sync_to_region(self, target_region: str, insights: list[RegionalInsight]) -> int:
        """
        Sync insights to target region.

        Args:
            target_region: Target region code
            insights: Insights to sync

        Returns:
            Number of insights synced
        """
        if not self.redis:
            return 0

        synced = 0
        for insight in insights:
            if insight.shared:
                key = f"learning:{target_region}:insights:{insight.insight_id}"
                await self.redis.set(
                    key,
                    json.dumps(
                        {
                            "insight_id": insight.insight_id,
                            "region_code": insight.region_code,
                            "category": insight.category,
                            "data": insight.data,
                            "created_at": insight.created_at.isoformat(),
                            "shared": True,
                        }
                    ),
                )
                synced += 1

        logger.info(f"Synced {synced} insights to {target_region}")
        return synced

    async def get_global_patterns(
        self,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get patterns that exist across all regions.

        Returns: List[Any] of global patterns  # TODO(TYPE): replace Any with concrete type
        """
        # This is a simplified version
        # In production, you'd use a central aggregator or consensus algorithm

        if not self.redis:
            return []

        # Get shared insights from all regions
        pattern = "learning:*:insights:*"
        all_keys = await self.redis.keys(pattern)

        patterns: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        categories: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key in all_keys:
            data = await self.redis.get(key)
            if data:
                parsed = json.loads(data)
                category = parsed.get("category")
                if category:
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(parsed)

        # Find categories that appear in multiple regions
        for category, items in categories.items():
            regions = {i.get("region_code", "unknown") for i in items}
            if len(regions) > 1:
                patterns.append(
                    {
                        "type": "global_pattern",
                        "category": category,
                        "regions": list(regions),
                        "occurrence_count": len(items),
                        "confidence": min(len(regions) * 0.25, 0.95),
                    }
                )

        return patterns


# Convenience functions for regional learning
async def get_regional_context() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current regional context."""
    region = RegionManager().get_current_region()
    learner = RegionalPreferenceLearner(region)
    return learner.get_regional_context()


async def store_with_region(
    insight_id: str,
    category: str,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    share_across_regions: bool = False,
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> RegionalInsight:
    """Store insight with region info."""
    store = RegionalLearningStore(redis_client)
    return await store.store_regional_insight(insight_id, category, data, share_across_regions)
