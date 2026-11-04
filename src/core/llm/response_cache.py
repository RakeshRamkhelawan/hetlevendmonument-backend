"""
LLM Response Cache - Phase 2 Response Caching System
Provides intelligent caching for LLM responses with TTL and optimization
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cached LLM response entry"""

    response: str
    timestamp: datetime
    ttl_seconds: int
    model: str
    token_count: int
    cost: float


class ResponseCache:
    """LLM Response caching system"""

    def __init__(self) -> None:
        self.cache: dict[str, CacheEntry] = {}
        self.hits = 0
        self.misses = 0
        self.total_saved_cost = 0.0

    def _generate_key(self, prompt: str, model: str, temperature: float = 0.7) -> str:
        """Generate cache key from prompt and parameters"""
        key_data = f"{prompt}|{model}|{temperature}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def get(self, prompt: str, model: str, temperature: float = 0.7) -> str | None:
        """Get cached response if available"""
        key = self._generate_key(prompt, model, temperature)

        if key in self.cache:
            entry = self.cache[key]

            # Check if expired
            if datetime.now(timezone.utc) - entry.timestamp > timedelta(seconds=entry.ttl_seconds):
                del self.cache[key]
                self.misses += 1
                return None

            self.hits += 1
            self.total_saved_cost += entry.cost
            logger.info(f"Cache HIT for model {model}")
            return entry.response

        self.misses += 1
        logger.info(f"Cache MISS for model {model}")
        return None

    def set(
        self,
        prompt: str,
        response: str,
        model: str,
        temperature: float = 0.7,
        ttl_seconds: int = 3600,
        token_count: int = 0,
        cost: float = 0.0,
    ) -> None:
        """Cache LLM response"""
        key = self._generate_key(prompt, model, temperature)

        entry = CacheEntry(
            response=response,
            timestamp=datetime.now(timezone.utc),
            ttl_seconds=ttl_seconds,
            model=model,
            token_count=token_count,
            cost=cost,
        )

        self.cache[key] = entry
        logger.info(f"Cached response for model {model} (TTL: {ttl_seconds}s)")

    def clear(self) -> None:
        """Clear all cached responses"""
        cleared_count = len(self.cache)
        self.cache.clear()
        logger.info(f"Cleared {cleared_count} cached responses")

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "total_entries": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate_percent": round(hit_rate, 2),
            "total_saved_cost": round(self.total_saved_cost, 4),
            "cache_efficiency": "high" if hit_rate > 70 else "medium" if hit_rate > 40 else "low",
        }

    def cleanup_expired(self) -> None:
        """Remove expired cache entries"""
        now = datetime.now(timezone.utc)
        expired_keys: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for key, entry in self.cache.items():
            if now - entry.timestamp > timedelta(seconds=entry.ttl_seconds):
                expired_keys.append(key)

        for key in expired_keys:
            del self.cache[key]

        if expired_keys:
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")


# Global cache instance
_response_cache: ResponseCache | None = None


def get_response_cache() -> ResponseCache:
    """Get global response cache instance"""
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache()
    return _response_cache


# Compatibility exports
def clear_cache() -> None:
    """Clear response cache"""
    cache = get_response_cache()
    cache.clear()


def get_cache_stats() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get cache statistics"""
    cache = get_response_cache()
    return cache.get_stats()
