"""
Redis caching layer for Learning and Adaptation rules.

Provides:
- Cache for active adaptation rules (TTL: 5 minutes)
- Cache invalidation on rule updates
- Fallback to database on cache miss
"""

import json
import logging
from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.loop import AdaptationRule
from src.core.learning.service import AdaptationRuleService

logger = logging.getLogger(__name__)

# Cache TTL settings
RULE_CACHE_TTL = 300  # 5 minutes
STATS_CACHE_TTL = 60  # 1 minute


class RuleCache:
    """
    Redis cache for adaptation rules.

    Usage:
        cache = RuleCache(redis_client)
        rules = await cache.get_active_rules(tenant_id)
        if rules is None:
            rules = await db.fetch_active_rules(tenant_id)
            await cache.set_active_rules(tenant_id, rules)
    """

    def __init__(
        self,
        redis_client: Any | None = None,  # TODO(TYPE): Any -- redis.asyncio.Redis or compatible client
    ) -> None:
        self._redis = redis_client
        self._enabled = redis_client is not None

    def _key(self, tenant_id: str, suffix: str = "rules") -> str:
        """Generate cache key for tenant."""
        return f"adaptation_rules:{tenant_id}:{suffix}"

    def _rule_to_dict(
        self, rule: AdaptationRule
    ) -> dict[str, Any]:  # TODO(TYPE): Any -- mixed-value dict: id(str), confidence(float), active(bool), etc.
        """Convert AdaptationRule to dictionary for JSON serialization."""
        return {
            "id": rule.id,
            "rule_type": rule.rule_type,
            "trigger_keywords": rule.trigger_keywords,
            "trigger_patterns": rule.trigger_patterns,
            "target_supervisor": rule.target_supervisor,
            "target_agent": rule.target_agent,
            "confidence": rule.confidence,
            "priority": rule.priority,
            "times_applied": rule.times_applied,
            "success_rate": rule.success_rate,
            "active": rule.active,
        }

    def _dict_to_rule(self, data: dict[str, Any]) -> AdaptationRule:  # TODO(TYPE): replace Any with concrete type
        """Convert dictionary to AdaptationRule."""
        return AdaptationRule(**data)

    async def get_active_rules(self, tenant_id: str) -> list[AdaptationRule] | None:
        """
        Get active rules from cache.

        Returns: List of AdaptationRule objects, or None on cache miss
        """
        if not self._enabled or self._redis is None:
            return None

        redis = self._redis
        try:
            key = self._key(tenant_id, "active")
            data = await redis.get(key)

            if data is None:
                logger.debug(f"Cache miss for tenant {tenant_id}")
                return None

            rules_data = json.loads(data)
            rules = [self._dict_to_rule(r) for r in rules_data]
            logger.debug(f"Cache hit: {len(rules)} rules for tenant {tenant_id}")
            return rules

        except Exception as e:
            logger.warning(f"Cache get error: {e}")
            return None

    async def set_active_rules(
        self, tenant_id: str, rules: list[AdaptationRule], ttl: int = RULE_CACHE_TTL
    ) -> bool:
        """
        Store active rules in cache.

        Args:
            tenant_id: Tenant identifier
            rules: List of AdaptationRule objects to cache
            ttl: Time to live in seconds

        Returns:
            True if successful
        """
        if not self._enabled or self._redis is None:
            return False

        redis = self._redis
        try:
            key = self._key(tenant_id, "active")
            rules_data = [self._rule_to_dict(r) for r in rules]
            await redis.setex(key, ttl, json.dumps(rules_data))
            logger.debug(f"Cached {len(rules)} rules for tenant {tenant_id}")
            return True

        except Exception as e:
            logger.warning(f"Cache set error: {e}")
            return False

    async def invalidate(self, tenant_id: str) -> bool:
        """
        Invalidate cache for a tenant.

        Call this when rules are modified.

        Returns:
            True if successful
        """
        if not self._enabled or self._redis is None:
            return False

        redis = self._redis
        try:
            key = self._key(tenant_id, "active")
            await redis.delete(key)
            logger.debug(f"Cache invalidated for tenant {tenant_id}")
            return True

        except Exception as e:
            logger.warning(f"Cache invalidate error: {e}")
            return False

    async def get_stats(self, tenant_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get cached stats for a tenant."""
        if not self._enabled or self._redis is None:
            return None

        redis = self._redis
        try:
            key = self._key(tenant_id, "stats")
            data = await redis.get(key)
            return json.loads(data) if data else None

        except Exception as e:
            logger.warning(f"Cache stats error: {e}")
            return None

    async def set_stats(
        self,
        tenant_id: str,
        stats: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        ttl: int = STATS_CACHE_TTL,
    ) -> bool:
        """Store stats in cache."""
        if not self._enabled or self._redis is None:
            return False

        redis = self._redis
        try:
            key = self._key(tenant_id, "stats")
            await redis.setex(key, ttl, json.dumps(stats))
            return True

        except Exception as e:
            logger.warning(f"Cache set stats error: {e}")
            return False


class CachedAdaptationRuleService:
    """
    Wrapper around AdaptationRuleService with caching.

    This provides a transparent caching layer that:
    1. Checks cache first
    2. Falls back to database on miss
    3. Populates cache after DB fetch
    4. Invalidates cache on writes
    """

    def __init__(self, base_service: AdaptationRuleService, cache: RuleCache) -> None:
        self._service = base_service
        self._cache = cache

    async def get_active_rules(self, tenant_id: str, limit: int = 100) -> list[AdaptationRule]:
        """Get active rules with caching."""
        # Try cache first
        cached_rules = await self._cache.get_active_rules(tenant_id)
        if cached_rules is not None:
            return cached_rules[:limit]

        # Cache miss - fetch from DB
        rules = await self._service.get_active_rules(tenant_id, limit)

        # Populate cache
        await self._cache.set_active_rules(tenant_id, rules)

        return rules

    async def create_rule(self, tenant_id: str, **kwargs: Any) -> AdaptationRule:
        """Create rule and invalidate cache."""
        rule = await self._service.create_rule(tenant_id, **kwargs)

        # Invalidate cache so next read gets fresh data
        await self._cache.invalidate(tenant_id)

        return rule

    async def deactivate_rule(self, rule_id: str, tenant_id: str) -> bool:
        """Deactivate rule and invalidate cache."""
        result = await self._service.deactivate_rule(rule_id, tenant_id)

        if result:
            await self._cache.invalidate(tenant_id)

        return result

    async def activate_rule(self, rule_id: str, tenant_id: str) -> bool:
        """Activate rule and invalidate cache."""
        result = await self._service.activate_rule(rule_id, tenant_id)

        if result:
            await self._cache.invalidate(tenant_id)

        return result

    async def get_rule_stats(self, tenant_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get stats with caching."""
        # Try cache first
        cached_stats = await self._cache.get_stats(tenant_id)
        if cached_stats is not None:
            return cached_stats

        # Cache miss
        stats = await self._service.get_rule_stats(tenant_id)

        # Populate cache
        await self._cache.set_stats(tenant_id, stats)

        return stats

    # Delegate other methods directly to base service
    async def get_rules_for_routing(self, tenant_id: str, query: str) -> AdaptationRule | None:
        """Get rules for routing (uses cached get_active_rules internally)."""
        rules = await self.get_active_rules(tenant_id)

        if not rules:
            return None

        query_lower = query.lower()
        best_rule = None
        best_score = 0.0

        for rule in rules:
            score = self._calculate_match_score(rule, query_lower)
            if score > best_score and score >= 0.5:
                best_score = score
                best_rule = rule

        return best_rule

    def _calculate_match_score(self, rule: AdaptationRule, query: str) -> float:
        """Calculate how well a rule matches a query."""
        if not rule.trigger_keywords:
            return 0.0

        matches = sum(1 for kw in rule.trigger_keywords if kw.lower() in query)
        if matches == 0:
            return 0.0

        coverage = matches / len(rule.trigger_keywords)
        priority_weight = (rule.priority or 0) / 10.0
        confidence = rule.confidence or 0.0
        score = coverage * confidence * (0.5 + 0.5 * priority_weight)

        return min(score, 1.0)


# Factory function for creating cached service
def create_cached_adaptation_service(
    db_session: AsyncSession,
    redis_client: Any | None = None,  # TODO(TYPE): Any -- redis.asyncio.Redis or compatible client
) -> CachedAdaptationRuleService:
    """
    Create an AdaptationRuleService with Redis caching.

    Usage:
        service = create_cached_adaptation_service(db_session, redis_client)
        rules = await service.get_active_rules(tenant_id)
    """
    base_service = AdaptationRuleService(db_session)
    cache = RuleCache(redis_client)

    return CachedAdaptationRuleService(base_service, cache)
