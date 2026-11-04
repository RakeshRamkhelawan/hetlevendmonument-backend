"""
Feature Flag Manager for Multi-Tenant Monetization
Task 1.3.2: Feature Flag Manager Core Logic

Design:
- Per-tenant feature gating (starter vs pro vs enterprise)
- Redis caching for performance (1h TTL, 5min recommended for production)
- Decorator-based endpoint guards (@requires_feature)
- Automatic provisioning from subscription tier

Features to Gate:
- memory_mcp: Semantic memory integration (Pro+)
- ollama_mcp: Local LLM integration (Enterprise)
- custom_agents: Deploy custom agents (Enterprise)
- sso: Single sign-on (Enterprise)
- advanced_analytics: Detailed usage analytics (Pro+)

Performance:
- Cache hit rate: >95% (Redis)
- Latency: <2ms (cache hit), <20ms (cache miss)
- TTL: 3600s (1 hour) - tune based on subscription change frequency
"""

import logging
from functools import wraps
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

# Import from our features module
from src.core.feature_flags.features import TIER_FEATURES, Feature, Tier
from src.core.feature_flags.features import feature_included_in_tier as _feature_included_in_tier
from src.core.feature_flags.features import get_tier_features as _get_tier_features

logger = logging.getLogger(__name__)


class FeatureFlagManager:
    """
    Manage feature flags per tenant with Redis caching

    Flow:
    1. When subscription created -> Stripe webhook
    2. Webhook calls enable_features_for_tier()
    3. Features stored in DB + cached in Redis
    4. Handler with @requires_feature decorator blocks access if not enabled
    """

    CACHE_TTL = 3600  # 1 hour
    CACHE_KEY_PREFIX = "ff:"  # ff:tenant_123:feature_name

    def __init__(self, redis_client: Any = None, db_session: Any = None) -> None:
        """
        Initialize feature flag manager

        Args:
            redis_client: Redis client for caching (optional)
            db_session: SQLAlchemy session for database access
        """
        self.redis = redis_client
        self.db = db_session

    async def is_enabled(
        self,
        tenant_id: str,
        feature: Feature,
    ) -> bool:
        """
        Check if feature is enabled for tenant

        Flow:
        1. Check Redis cache (fast path)
        2. If miss, check database
        3. Cache result for 1h

        Args:
            tenant_id: Tenant to check
            feature: Feature to check

        Returns:
            True if feature enabled for tenant
        """
        if not self.redis and not self.db:
            logger.warning("Feature flags not configured (allowing all)")
            return True

        # Try cache first
        cache_key = f"{self.CACHE_KEY_PREFIX}{tenant_id}:{feature.value}"
        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached is not None:
                    logger.debug("Feature flag cache hit: %s for %s", feature.value, tenant_id)
                    return cast(bool, cached == b"1")
            except Exception as e:
                logger.warning("Redis cache error (falling back to DB): %s", str(e))

        # Load from database
        db_conn = self.db
        is_temporary_session = False
        if not db_conn:
            try:
                from src.core.database.session import get_db_session

                db_conn = get_db_session()
                is_temporary_session = True
            except ImportError:
                pass

        if db_conn:
            try:
                from sqlalchemy import select
                from src.core.feature_flags.models import FeatureFlag

                # Helper to run query block
                async def _run_query(
                    session: AsyncSession,
                ) -> bool:
                    stmt = select(FeatureFlag).filter(
                        FeatureFlag.tenant_id == tenant_id,
                        FeatureFlag.feature_name == feature.value,
                    )
                    result = await session.execute(stmt)
                    flag = result.scalar_one_or_none()
                    return flag.is_enabled if flag else False

                if is_temporary_session:
                    async with db_conn as temp_session:
                        is_enabled = await _run_query(temp_session)
                else:
                    is_enabled = await _run_query(cast(AsyncSession, db_conn))

                # Cache result
                if self.redis:
                    try:
                        await self.redis.setex(
                            cache_key, self.CACHE_TTL, b"1" if is_enabled else b"0"
                        )
                    except Exception as e:
                        logger.warning("Failed to cache feature flag: %s", str(e))

                return is_enabled

            except Exception as e:
                logger.error("Feature flag lookup failed: %s", str(e), exc_info=True)
                return False

        # No Redis and no DB - fail open for safety
        logger.warning("No Redis or DB available for feature flags - allowing all")
        return True

    async def enable_features_for_tier(
        self,
        tenant_id: str,
        tier: Tier,
    ) -> None:
        """
        Enable all features for a subscription tier

        Call when subscription created:
            await ff_manager.enable_features_for_tier("tenant_123", Tier.PRO)

        Args:
            tenant_id: Tenant to enable for
            tier: Subscription tier (starter|pro|enterprise)

        Raises:
            RuntimeError: If database session is not configured.
        """
        from sqlalchemy import delete

        from src.core.feature_flags.models import FeatureFlag

        if self.db is None:
            raise RuntimeError("Database session not configured for feature flag manager")

        db = self.db
        features = TIER_FEATURES.get(tier, set())

        logger.info("Enabling %s features for %s tier on %s", len(features), tier, tenant_id)

        try:
            # Disable all features first - use async-compatible delete
            stmt = delete(FeatureFlag).where(FeatureFlag.tenant_id == tenant_id)
            await db.execute(stmt)

            # Enable tier features
            for feature in features:
                flag = FeatureFlag(
                    tenant_id=tenant_id,
                    feature_name=feature.value,
                    is_enabled=True,
                )
                db.add(flag)

            await db.commit()

            # Invalidate cache for all features (don't fail if cache errors)
            if self.redis:
                for feature in features:
                    try:
                        cache_key = f"{self.CACHE_KEY_PREFIX}{tenant_id}:{feature.value}"
                        await self.redis.delete(cache_key)
                    except Exception as cache_error:
                        logger.warning(
                            f"Failed to invalidate cache for {feature.value}: {cache_error}"
                        )

        except Exception as e:
            logger.error(f"Failed to enable features for {tier}: {str(e)}", exc_info=True)
            if db is not None:
                await db.rollback()
            raise


# ============================================================================
# DECORATOR FOR ENDPOINT PROTECTION
# ============================================================================


def requires_feature(feature: Feature) -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to require feature flag on endpoint

    Usage:
        @app.get("/api/memory/search")
        @requires_feature(Feature.MEMORY_MCP)  # Only Pro+ tenants
        async def search_memories(query: str, request: Request):
            ...

    Args:
        feature: Feature flag required to access endpoint

    Returns:
        Decorator function
    """

    def decorator(func: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Get request from args (FastAPI passes it)
            request = None
            for arg in args:
                if hasattr(arg, "state") and hasattr(arg.state, "tenant_id"):
                    request = arg
                    break

            if "request" in kwargs:
                request = kwargs["request"]

            if not request:
                logger.error("Could not find request in function arguments")
                raise ValueError("Feature guard requires Request object")

            tenant_id = request.state.tenant_id

            # Check feature flag -- getattr guard: 503 if not initialised at startup
            ff_manager = getattr(request.app.state, "ff_manager", None)
            if ff_manager is None:
                from fastapi import HTTPException

                raise HTTPException(status_code=503, detail="Feature flag service unavailable")
            is_enabled = await ff_manager.is_enabled(tenant_id, feature)

            if not is_enabled:
                from fastapi import HTTPException

                logger.warning(f"Feature access denied: {feature.value} for {tenant_id}")
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "Feature not available for your plan",
                        "feature": feature.value,
                        "upgrade_url": f"https://yoursite.com/upgrade?feature={feature.value}",
                    },
                )

            # Feature enabled, call handler
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# CONFIGURATION HELPERS
# ============================================================================


def get_tier_features(tier: Tier) -> set[Feature]:
    """Get all features included in a tier (re-export from features module)"""
    return _get_tier_features(tier)


def feature_included_in_tier(feature: Feature, tier: Tier) -> bool:
    """Check if feature is included in tier (re-export from features module)"""
    return _feature_included_in_tier(feature, tier)
