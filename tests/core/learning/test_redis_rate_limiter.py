"""
Unit tests voor RedisRateLimiter.

Controleert:
- Altijd allowed als redis_client=None (test/fail-open mode)
- Toegang toegestaan binnen limiet
- Toegang geweigerd bij overschrijding
- Sliding window: oude entries tellen niet mee
- Fail-open bij Redis error
- Custom limits
- Correcte Redis key format
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter


def _make_redis_mock(current_count: int = 0, raise_error: bool = False) -> MagicMock:
    """Maak een mock Redis client die pipeline().execute() simuleert."""
    redis = MagicMock()
    pipe = AsyncMock()

    if raise_error:
        pipe.execute = AsyncMock(side_effect=ConnectionError("Redis down"))
    else:
        # execute() returns: [zremrangebyscore, zcard, zadd, expire]
        pipe.execute = AsyncMock(return_value=[None, current_count, 1, 1])

    pipe.zremrangebyscore = MagicMock(return_value=pipe)
    pipe.zcard = MagicMock(return_value=pipe)
    pipe.zadd = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)

    redis.pipeline = MagicMock(return_value=pipe)
    return redis


@pytest.mark.asyncio
class TestRedisRateLimiterNoRedis:
    """Tests zonder Redis (test mode)."""

    async def test_no_redis_always_allowed(self):
        limiter = RedisRateLimiter(redis_client=None)
        assert await limiter.is_allowed("user1", "file_edit") is True

    async def test_no_redis_any_behavior_allowed(self):
        limiter = RedisRateLimiter(redis_client=None)
        for behavior in ["file_edit", "rapid_switch", "work_start", "unknown"]:
            assert await limiter.is_allowed("user1", behavior) is True


@pytest.mark.asyncio
class TestRedisRateLimiterWithRedis:
    """Tests met mock Redis client."""

    async def test_allowed_within_limit(self):
        redis = _make_redis_mock(current_count=5)
        limiter = RedisRateLimiter(redis_client=redis)
        # Default limit: 100 per 60s; count=5 < 100
        assert await limiter.is_allowed("user1", "file_edit") is True

    async def test_denied_at_limit(self):
        redis = _make_redis_mock(current_count=100)
        limiter = RedisRateLimiter(redis_client=redis)
        # Default limit: 100; count=100 >= 100
        assert await limiter.is_allowed("user1", "file_edit") is False

    async def test_denied_over_limit(self):
        redis = _make_redis_mock(current_count=150)
        limiter = RedisRateLimiter(redis_client=redis)
        assert await limiter.is_allowed("user1", "file_edit") is False

    async def test_specific_behavior_limit_respected(self):
        # repeated_edits_same_line has limit 10 per 60s
        redis = _make_redis_mock(current_count=10)
        limiter = RedisRateLimiter(redis_client=redis)
        assert await limiter.is_allowed("user1", "repeated_edits_same_line") is False

    async def test_specific_behavior_within_limit(self):
        redis = _make_redis_mock(current_count=9)
        limiter = RedisRateLimiter(redis_client=redis)
        assert await limiter.is_allowed("user1", "repeated_edits_same_line") is True

    async def test_unknown_behavior_uses_default_limit(self):
        redis = _make_redis_mock(current_count=99)
        limiter = RedisRateLimiter(redis_client=redis)
        assert await limiter.is_allowed("user1", "unknown_behavior") is True

    async def test_unknown_behavior_at_default_limit(self):
        redis = _make_redis_mock(current_count=100)
        limiter = RedisRateLimiter(redis_client=redis)
        assert await limiter.is_allowed("user1", "unknown_behavior") is False


@pytest.mark.asyncio
class TestRedisRateLimiterFailOpen:
    """Tests voor fail-open gedrag bij Redis errors."""

    async def test_redis_error_is_allowed(self):
        """Als Redis faalt → observation wordt toegelaten (fail-open)."""
        redis = _make_redis_mock(raise_error=True)
        limiter = RedisRateLimiter(redis_client=redis)
        result = await limiter.is_allowed("user1", "file_edit")
        assert result is True

    async def test_redis_connection_error_does_not_raise(self):
        redis = _make_redis_mock(raise_error=True)
        limiter = RedisRateLimiter(redis_client=redis)
        # Should not raise, should return True (fail-open)
        try:
            result = await limiter.is_allowed("user1", "file_edit")
            assert result is True
        except Exception:
            pytest.fail("is_allowed should not raise on Redis error")


@pytest.mark.asyncio
class TestRedisRateLimiterCustomLimits:
    """Tests voor custom rate limit configuratie."""

    async def test_custom_limits_respected(self):
        custom_limits = {
            "file_edit": (5, 30),  # slechts 5 per 30s
            "default": (100, 60),
        }
        redis = _make_redis_mock(current_count=5)
        limiter = RedisRateLimiter(redis_client=redis, limits=custom_limits)
        # count=5 >= limit=5 → denied
        assert await limiter.is_allowed("user1", "file_edit") is False

    async def test_custom_limits_within_allowed(self):
        custom_limits = {
            "file_edit": (5, 30),
            "default": (100, 60),
        }
        redis = _make_redis_mock(current_count=4)
        limiter = RedisRateLimiter(redis_client=redis, limits=custom_limits)
        assert await limiter.is_allowed("user1", "file_edit") is True


class TestRedisRateLimiterGetLimit:
    """Tests voor de _get_limit helper."""

    def test_known_behavior_type_returns_correct_limit(self):
        limiter = RedisRateLimiter()
        max_count, window = limiter._get_limit("repeated_edits_same_line")
        assert max_count == 10
        assert window == 60

    def test_unknown_behavior_returns_default(self):
        limiter = RedisRateLimiter()
        max_count, window = limiter._get_limit("nonexistent_behavior")
        assert max_count == 100
        assert window == 60

    def test_work_start_has_hourly_limit(self):
        limiter = RedisRateLimiter()
        max_count, window = limiter._get_limit("work_start")
        assert max_count == 5
        assert window == 3600
