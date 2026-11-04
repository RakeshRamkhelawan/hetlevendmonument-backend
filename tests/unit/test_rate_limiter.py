"""Tests for Redis rate limiter."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.security.rate_limiter import RedisRateLimiter


class TestRedisRateLimiter:
    """Test RedisRateLimiter script_sha typing."""

    @pytest.mark.unit
    def test_script_sha_initialized_as_none(self):
        """script_sha must be initialized as None and typed as str | None."""
        mock_redis = MagicMock()
        limiter = RedisRateLimiter(mock_redis)

        assert limiter.script_sha is None
        assert isinstance(limiter.script_sha, type(None))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_limit_loads_script_sha(self):
        """check_limit must load script_sha from Redis on first call."""
        mock_redis = AsyncMock()
        mock_redis.script_load.return_value = "abc123def456"
        mock_redis.evalsha.return_value = 1

        limiter = RedisRateLimiter(mock_redis)
        result = await limiter.check_limit("test_key", 100, 60)

        assert result is True
        assert limiter.script_sha == "abc123def456"
        mock_redis.script_load.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_limit_reuses_script_sha(self):
        """check_limit must reuse cached script_sha on subsequent calls."""
        mock_redis = AsyncMock()
        mock_redis.script_load.return_value = "abc123def456"
        mock_redis.evalsha.return_value = 1

        limiter = RedisRateLimiter(mock_redis)

        # First call
        await limiter.check_limit("test_key", 100, 60)
        call_count_first = mock_redis.script_load.call_count

        # Second call - should reuse cached SHA
        await limiter.check_limit("test_key", 100, 60)
        call_count_second = mock_redis.script_load.call_count

        assert call_count_first == call_count_second == 1  # Only called once total
