"""
Redis Rate Limiter - Sliding Window Algorithm

Provides atomic rate limiting using Redis Lua scripts to prevent
race conditions in high-concurrency environments.

Part of SA-2.2 and SA-2.3 implementation.
"""

from __future__ import annotations

from typing import Any, cast

import redis.asyncio as redis


class RedisRateLimiter:
    """
    Rate limiter using Redis with atomic Lua script execution.

    Implements a sliding window counter algorithm that:
    - Checks current request count
    - Increments counter atomically
    - Sets TTL on first request
    - Returns allow/deny decision
    """

    def __init__(self, redis_client: redis.Redis) -> None:  # type: ignore[type-arg]
        self.redis = redis_client
        # Lua script for sliding window rate limiting
        # KEYS[1]: The rate limit key (e.g., "rate_limit:ip:127.0.0.1")
        # ARGV[1]: The window size in seconds (e.g., 60)
        # ARGV[2]: The max limit (e.g., 100)
        self.lua_script = """
        local key = KEYS[1]
        local window = tonumber(ARGV[1])
        local limit = tonumber(ARGV[2])

        local current = redis.call("INCR", key)
        if current == 1 then
            redis.call("EXPIRE", key, window)
        end

        if current > limit then
            return 0 -- Denied
        end
        return 1 -- Allowed
        """
        self.script_sha: str | None = None

    async def check_limit(self, key: str, limit: int, window: int) -> bool:
        """
        Check if a request is within rate limits.

        Args:
            key: The rate limit key (e.g., "rate_limit:user:123")
            limit: Maximum number of requests allowed
            window: Time window in seconds

        Returns:
            True if allowed, False if rate limited
        """
        if not self.script_sha:
            # Preload script for performance
            _sha_result = cast(  # TODO(TYPE): replace Any with concrete type
                Any, self.redis
            ).script_load(self.lua_script)
            sha = (
                await _sha_result if hasattr(_sha_result, "__await__") else _sha_result
            )  # noqa: E501
            self.script_sha = str(sha)

        # redis.asyncio stubs mismatch: evalsha accepts str/int varargs at runtime
        result = cast(  # TODO(TYPE): replace Any with concrete type
            Any,
            await cast(Any, self.redis).evalsha(  # TODO(TYPE): replace Any with concrete type
                self.script_sha,
                1,
                key,
                str(window),
                str(limit),
            ),
        )
        return bool(result == 1)

    def _generate_key(self, identifier: str, endpoint: str) -> str:
        """
        Generate a standardized rate limit key.

        Args:
            identifier: User ID, IP address, or other identifier
            endpoint: API endpoint being accessed

        Returns:
            Formatted key string
        """
        return f"rate_limit:{identifier}:{endpoint}"

    async def check_request(
        self, identifier: str, endpoint: str, limit: int = 100, window: int = 60
    ) -> bool:
        """
        High-level method to check if a request should be allowed.

        Args:
            identifier: User ID, IP address, or API key
            endpoint: The API endpoint being accessed
            limit: Maximum requests per window (default: 100)
            window: Time window in seconds (default: 60)

        Returns:
            True if allowed, False if rate limited
        """
        key = self._generate_key(identifier, endpoint)
        return await self.check_limit(key, limit, window)
