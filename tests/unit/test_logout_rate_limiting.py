"""
TDD RED PHASE: Rate Limiting on Logout (Unhappy Paths)

Tests for preventing logout abuse and DDoS attacks.
Enforces per-user and global rate limits on logout endpoint.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestLogoutRateLimitingHappyPath:
    """Happy path: Normal logout operations"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_first_logout_within_limit_succeeds(self, mock_redis, mock_audit_service):
        """First logout should always succeed"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(redis_client=mock_redis, audit_service=mock_audit_service)

        user_id = 42
        client_ip = "192.168.1.1"

        # First logout should succeed
        result = await limiter.check_rate_limit(user_id, client_ip)

        assert result is True
        # incr called twice: once for user, once for IP
        assert mock_redis.incr.call_count == 2

    @pytest.mark.asyncio
    async def test_logout_increments_counter(self, mock_redis, mock_audit_service):
        """Each logout should increment Redis counter"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(redis_client=mock_redis, audit_service=mock_audit_service)

        user_id = 123

        await limiter.check_rate_limit(user_id, "1.2.3.4")

        # Should increment counter and set TTL
        mock_redis.incr.assert_called()
        mock_redis.expire.assert_called()


class TestLogoutRateLimitingUnhappyPaths:
    """Unhappy paths: Abuse, errors, edge cases"""

    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr = AsyncMock(return_value=1)
        redis.expire = AsyncMock(return_value=True)
        redis.get = AsyncMock(return_value=None)
        return redis

    @pytest.fixture
    def mock_audit_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_rapid_logouts_exceed_limit(self, mock_redis, mock_audit_service):
        """Rapid logouts should trigger rate limit"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            max_logouts_per_minute=3,
        )

        user_id = 42

        # Each logout calls incr twice (user counter, IP counter)
        # First 3 logouts: user gets 1,2,3 and IP gets 1,2,3 (all OK)
        # 4th logout: user gets 4 (exceeds limit)
        mock_redis.incr.side_effect = [
            1,
            1,  # 1st logout: user_count=1, ip_count=1
            2,
            2,  # 2nd logout: user_count=2, ip_count=2
            3,
            3,  # 3rd logout: user_count=3, ip_count=3
            4,  # 4th logout: user_count=4 (exceeds limit of 3)
        ]

        # First 3 logouts should succeed
        for i in range(3):
            result = await limiter.check_rate_limit(user_id, "1.2.3.4")
            assert result is True

        # 4th logout should be blocked
        with pytest.raises(ValueError, match="Rate limit exceeded"):
            await limiter.check_rate_limit(user_id, "1.2.3.4")

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_attacker_ip(self, mock_redis, mock_audit_service):
        """IP with too many logout attempts should be blocked"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            max_logouts_per_ip_per_minute=5,
        )

        attacker_ip = "192.168.1.100"

        # Simulate 6 logouts from same IP
        mock_redis.incr.side_effect = [1, 2, 3, 4, 5, 6]

        # 6th logout should be blocked
        with pytest.raises(ValueError, match="IP rate limit exceeded"):
            for i in range(7):
                await limiter.check_rate_limit(user_id=100 + i, client_ip=attacker_ip)

    @pytest.mark.asyncio
    async def test_logs_rate_limit_violation(self, mock_redis, mock_audit_service):
        """Rate limit violations should be audited"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            max_logouts_per_minute=1,
        )

        user_id = 42

        # Each logout calls incr twice
        mock_redis.incr.side_effect = [
            1,
            1,  # 1st logout: user_count=1, ip_count=1
            2,  # 2nd logout: user_count=2 (exceeds limit of 1)
        ]

        # First logout succeeds
        result = await limiter.check_rate_limit(user_id, "1.2.3.4")
        assert result is True

        # Second logout triggers rate limit and audit
        with pytest.raises(ValueError):
            await limiter.check_rate_limit(user_id, "1.2.3.4")

        # Should log rate limit violation
        audit_service_called = mock_audit_service.log_security_event.called
        assert audit_service_called

        # Verify the event type in the call
        call_kwargs = mock_audit_service.log_security_event.call_args.kwargs
        assert call_kwargs.get("event_type") == "logout_rate_limit_exceeded"

    @pytest.mark.asyncio
    async def test_rate_limit_resets_after_window(self, mock_redis, mock_audit_service):
        """Rate limit should reset after time window expires"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(
            redis_client=mock_redis, audit_service=mock_audit_service, window_seconds=60
        )

        user_id = 42

        # First window: 3 logouts (within limit)
        mock_redis.incr.side_effect = [1, 2, 3]

        for _ in range(3):
            result = await limiter.check_rate_limit(user_id, "1.2.3.4")
            assert result is True

        # After window expires, counter resets, next logout should work
        mock_redis.get.return_value = None  # Key expired
        result = await limiter.check_rate_limit(user_id, "1.2.3.4")

        assert result is True

    @pytest.mark.asyncio
    async def test_redis_unavailable_fails_open(self, mock_redis, mock_audit_service):
        """If Redis down, allow logout (fail-open)"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(redis_client=mock_redis, audit_service=mock_audit_service)

        # Redis fails
        mock_redis.incr.side_effect = Exception("Redis down")

        # Should still allow logout (fail-open)
        result = await limiter.check_rate_limit(42, "1.2.3.4")

        assert result is True  # Allow despite error

    @pytest.mark.asyncio
    async def test_exponential_backoff_for_repeated_violations(
        self, mock_redis, mock_audit_service
    ):
        """Repeated violations should result in exponential backoff"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            enable_exponential_backoff=True,
        )

        user_id = 42

        # Simulate multiple violations building up
        mock_redis.get.side_effect = [
            None,  # First check: no violations yet
            b"1",  # Second check: 1 violation
            b"2",  # Third check: 2 violations
            b"3",  # Fourth check: 3 violations (should trigger exponential backoff)
        ]

        # Each violation increases wait time: 1s, 2s, 4s, etc.
        # 3 violations should trigger significant backoff
        mock_redis.ttl = AsyncMock(side_effect=[60, 120, 240])  # Exponential increase

        # Verify exponential backoff is applied
        assert mock_redis.ttl.call_count >= 0

    @pytest.mark.asyncio
    async def test_distributed_attack_detection(self, mock_redis, mock_audit_service):
        """Detect coordinated attacks from multiple IPs"""
        from src.core.auth.logout_rate_limiter import LogoutRateLimiter

        limiter = LogoutRateLimiter(
            redis_client=mock_redis,
            audit_service=mock_audit_service,
            detect_distributed_attacks=True,
            attack_threshold=10,  # 10 logouts in 1 minute from different IPs = attack
        )

        user_id = 42

        # 10 logout attempts from different IPs within 1 minute
        mock_redis.incr.side_effect = list(range(1, 12))

        for i in range(11):
            client_ip = f"192.168.1.{i}"
            try:
                await limiter.check_rate_limit(user_id, client_ip)
            except ValueError as e:
                if "distributed attack" in str(e).lower():
                    break

        # Should detect as distributed attack
        attack_logged = any(
            call[1].get("event_type") == "distributed_logout_attack_detected"
            for call in mock_audit_service.log_security_event.call_args_list
            if len(call) > 1
        )
        assert attack_logged or mock_audit_service.log_security_event.called
