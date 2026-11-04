# src/core/services/subscription_cache.py
import logging
from typing import Optional

from src.core.caching.cache_layer import AsyncCacheLayer, get_cache


class TenantSubscriptionCache:
    """
    Redis-backed cache layer for storing and retrieving tenant subscription info
    asynchronously using JSON serialization.
    """

    def __init__(
        self,
        tenant_id: int,
        cache_layer: Optional[AsyncCacheLayer] = None,
        ttl: int = 600,
        key_prefix: str = "tenant_sub",
    ) -> None:
        self.tenant_id = tenant_id
        self._cache_layer = cache_layer
        self.ttl = ttl
        self.key_prefix = key_prefix
        self.logger = logging.getLogger(__name__)

    async def _get_cache_layer(self) -> AsyncCacheLayer:
        """Helper to get or initialize the async cache layer."""
        if self._cache_layer is None:
            self._cache_layer = await get_cache()
        return self._cache_layer

    def _key(self) -> str:
        """Generate Redis key for the current tenant."""
        return f"{self.key_prefix}:{self.tenant_id}"

    async def get(self) -> Optional[dict[str, str]]:
        """
        Retrieve cached subscription details.

        Returns:
            Dict containing 'tier' and 'status', or None on miss/error.
        """
        try:
            cache = await self._get_cache_layer()
            data = await cache.get(self._key())

            if data is None:
                return None

            if isinstance(data, dict) and "tier" in data and "status" in data:
                return {"tier": str(data["tier"]), "status": str(data["status"])}

            return None
        except Exception as e:
            self.logger.error(
                f"Error retrieving subscription cache for tenant {self.tenant_id}: {e}",
                exc_info=True,
            )
            return None

    async def set(self, tier: str, status: str) -> bool:
        """
        Cache subscription details.

        Args:
            tier: Subscription tier name (e.g. 'pro')
            status: Subscription status (e.g. 'active')

        Returns:
            True if set operation succeeded, False otherwise.
        """
        try:
            cache = await self._get_cache_layer()
            value = {"tier": tier, "status": status}
            success = await cache.set(self._key(), value, self.ttl)
            return bool(success)
        except Exception as e:
            self.logger.error(
                f"Error setting subscription cache for tenant {self.tenant_id}: {e}", exc_info=True
            )
            return False

    async def delete(self) -> bool:
        """
        Invalidate cached subscription details.

        Returns:
            True if delete operation succeeded, False otherwise.
        """
        try:
            cache = await self._get_cache_layer()
            success = await cache.delete(self._key())
            return bool(success)
        except Exception as e:
            self.logger.error(
                f"Error deleting subscription cache for tenant {self.tenant_id}: {e}", exc_info=True
            )
            return False
