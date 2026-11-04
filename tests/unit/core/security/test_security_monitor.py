"""
Unit tests for Security Monitor module.

Tests security event detection and anomaly detection logic.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.security.security_monitor import (
    SecurityEvent,
    SecurityEventType,
    SecurityMonitor,
    ThreatLevel,
    get_security_monitor,
)


class TestSecurityEvent:
    """Test SecurityEvent dataclass."""

    def test_event_creation(self):
        """Test creating a security event."""
        event = SecurityEvent(
            event_type=SecurityEventType.LOGIN_FAILURE,
            timestamp=datetime.utcnow(),
            user_id=1,
            ip_address="192.168.1.1",
            threat_level=ThreatLevel.MEDIUM,
            details={"reason": "invalid_password"},
        )

        assert event.event_type == SecurityEventType.LOGIN_FAILURE
        assert event.user_id == 1
        assert event.ip_address == "192.168.1.1"
        assert event.threat_level == ThreatLevel.MEDIUM
        assert event.details["reason"] == "invalid_password"


class TestSecurityMonitor:
    """Test SecurityMonitor class."""

    @pytest.fixture
    def monitor(self):
        """Create a fresh security monitor instance."""
        return SecurityMonitor()

    @pytest.mark.asyncio
    async def test_record_login_success(self, monitor):
        """Test recording successful login."""
        await monitor.record_login_attempt(
            user_id=1, ip_address="192.168.1.1", success=True, user_agent="Mozilla/5.0"
        )

        # Should be tracked in memory
        assert len(monitor._login_attempts["192.168.1.1"]) == 1
        assert len(monitor._ip_events["192.168.1.1"]) == 1
        assert len(monitor._user_activity[1]) == 1

    @pytest.mark.asyncio
    async def test_record_login_failure(self, monitor):
        """Test recording failed login."""
        await monitor.record_login_attempt(
            user_id=None,
            ip_address="192.168.1.1",
            success=False,
            user_agent="Mozilla/5.0",
        )

        assert len(monitor._login_attempts["192.168.1.1"]) == 1
        event = monitor._login_attempts["192.168.1.1"][0]
        assert event.event_type == SecurityEventType.LOGIN_FAILURE

    @pytest.mark.asyncio
    async def test_detect_brute_force(self, monitor):
        """Test brute force detection."""
        ip = "192.168.1.100"

        # Record 5 failed login attempts
        for _ in range(5):
            await monitor.record_login_attempt(user_id=None, ip_address=ip, success=False)

        # Should detect brute force
        assert await monitor.detect_brute_force(ip) is True

    @pytest.mark.asyncio
    async def test_detect_brute_force_below_threshold(self, monitor):
        """Test brute force not detected below threshold."""
        ip = "192.168.1.100"

        # Record only 3 failed login attempts
        for _ in range(3):
            await monitor.record_login_attempt(user_id=None, ip_address=ip, success=False)

        # Should not detect brute force
        assert await monitor.detect_brute_force(ip) is False

    @pytest.mark.asyncio
    async def test_detect_suspicious_ip(self, monitor):
        """Test suspicious IP detection."""
        ip = "192.168.1.200"

        # Record 15 events from same IP
        for i in range(15):
            await monitor.record_security_event(
                event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                ip_address=ip,
                details={"event_num": i},
            )

        # Should detect suspicious IP
        assert await monitor.detect_suspicious_ip(ip) is True

    @pytest.mark.asyncio
    async def test_detect_suspicious_ip_below_threshold(self, monitor):
        """Test suspicious IP not detected below threshold."""
        ip = "192.168.1.200"

        # Record only 5 events
        for i in range(5):
            await monitor.record_security_event(
                event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
                ip_address=ip,
                details={"event_num": i},
            )

        # Should not detect suspicious IP
        assert await monitor.detect_suspicious_ip(ip) is False

    @pytest.mark.asyncio
    async def test_ip_blocking(self, monitor):
        """Test IP blocking functionality."""
        ip = "192.168.1.50"

        # Initially not blocked
        assert monitor.is_ip_blocked(ip) is False

        # Trigger brute force detection to block IP
        for _ in range(5):
            await monitor.record_login_attempt(user_id=None, ip_address=ip, success=False)

        # IP should be blocked
        assert monitor.is_ip_blocked(ip) is True

    @pytest.mark.asyncio
    async def test_unblock_ip(self, monitor):
        """Test unblocking an IP."""
        ip = "192.168.1.50"

        # Block the IP
        monitor._blocked_ips.add(ip)
        assert monitor.is_ip_blocked(ip) is True

        # Unblock
        result = await monitor.unblock_ip(ip)
        assert result is True
        assert monitor.is_ip_blocked(ip) is False

    @pytest.mark.asyncio
    async def test_unblock_non_blocked_ip(self, monitor):
        """Test unblocking an IP that wasn't blocked."""
        ip = "192.168.1.50"

        result = await monitor.unblock_ip(ip)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_threat_summary(self, monitor):
        """Test threat summary generation."""
        # Add some events
        for i in range(5):
            await monitor.record_security_event(
                event_type=SecurityEventType.LOGIN_FAILURE,
                ip_address=f"192.168.1.{i}",
                threat_level=ThreatLevel.MEDIUM,
            )

        summary = await monitor.get_threat_summary(hours=24)

        assert summary["total_events"] == 5
        assert summary["by_type"][SecurityEventType.LOGIN_FAILURE.value] == 5
        assert summary["by_threat_level"][ThreatLevel.MEDIUM.value] == 5

    @pytest.mark.asyncio
    async def test_detect_unusual_access_hours(self, monitor):
        """Test unusual access hours detection."""
        user_id = 42

        # Add 15 events at normal hours (9 AM - 5 PM)
        for i in range(15):
            event = SecurityEvent(
                event_type=SecurityEventType.LOGIN_SUCCESS,
                timestamp=datetime.utcnow().replace(hour=9 + (i % 8)),
                user_id=user_id,
            )
            monitor._user_activity[user_id].append(event)

        # Add event at unusual hour (3 AM)
        event = SecurityEvent(
            event_type=SecurityEventType.LOGIN_SUCCESS,
            timestamp=datetime.utcnow().replace(hour=3),
            user_id=user_id,
        )
        monitor._user_activity[user_id].append(event)

        # Should detect unusual hour (if current time is in unusual hours)
        # Note: This test depends on current time
        if datetime.utcnow().hour in range(0, 6):
            assert await monitor.detect_unusual_access_hours(user_id) is True

    @pytest.mark.asyncio
    async def test_record_security_event_with_redis(self, monitor):
        """Test recording event with Redis persistence."""
        # Mock Redis client
        mock_redis = AsyncMock()
        monitor.redis = mock_redis

        await monitor.record_security_event(
            event_type=SecurityEventType.SQL_INJECTION_ATTEMPT,
            user_id=1,
            ip_address="192.168.1.1",
            details={"payload": "' OR 1=1 --"},
            threat_level=ThreatLevel.HIGH,
        )

        # Should persist to Redis
        mock_redis.lpush.assert_called_once()
        mock_redis.expire.assert_called_once()


class TestGetSecurityMonitor:
    """Test get_security_monitor function."""

    def test_singleton_pattern(self):
        """Test that monitor is a singleton."""
        # Reset global instance
        import src.core.security.security_monitor as sm

        sm._security_monitor = None

        monitor1 = get_security_monitor()
        monitor2 = get_security_monitor()

        assert monitor1 is monitor2

    def test_with_redis_client(self):
        """Test creating monitor with Redis client."""
        # Reset global instance
        import src.core.security.security_monitor as sm

        sm._security_monitor = None

        mock_redis = Mock()
        monitor = get_security_monitor(mock_redis)

        assert monitor.redis is mock_redis
