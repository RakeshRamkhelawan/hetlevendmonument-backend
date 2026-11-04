"""
Security Monitoring & Anomaly Detection

Detects suspicious activity and potential security threats:
- Brute force attempts
- Unusual access patterns
- Privilege escalation attempts
- Data exfiltration patterns

Usage:
    from src.core.security.security_monitor import SecurityMonitor

    monitor = SecurityMonitor()
    monitor.record_login_attempt(user_id, ip_address, success)

    if monitor.detect_brute_force(ip_address):
        alert_security_team("Brute force detected", ip_address)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Deque, Dict, List, Optional, Set

from src.core.typing import AsyncRedisClient
from loguru import logger

from src.core.database.redis import ensure_async


from src.core.security.types import ThreatLevel


class SecurityEventType(Enum):
    """Types of security events."""

    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    BRUTE_FORCE_ATTEMPT = "brute_force_attempt"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    UNUSUAL_ACCESS_PATTERN = "unusual_access_pattern"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"


@dataclass
class SecurityEvent:
    """Security event record."""

    event_type: SecurityEventType
    timestamp: datetime
    user_id: int | None = None
    ip_address: str | None = None
    details: dict[str, str] = field(default_factory=dict)
    threat_level: ThreatLevel = ThreatLevel.LOW


class SecurityMonitor:
    """
    Monitors security events and detects anomalies.

    Uses in-memory tracking with Redis persistence for distributed setups.
    """

    # Thresholds for anomaly detection
    BRUTE_FORCE_THRESHOLD = 5  # Failed logins in window
    BRUTE_FORCE_WINDOW = 300  # 5 minutes
    SUSPICIOUS_IP_THRESHOLD = 10  # Events per hour
    UNUSUAL_HOURS = range(0, 6)  # Midnight to 6 AM

    def __init__(self, redis_client: AsyncRedisClient | None = None) -> None:
        self.redis = redis_client
        # In-memory storage (use Redis in production)
        self._login_attempts: dict[str, Deque[SecurityEvent]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._ip_events: dict[str, Deque[SecurityEvent]] = defaultdict(lambda: deque(maxlen=1000))
        self._user_activity: dict[int, Deque[SecurityEvent]] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._blocked_ips: set[str] = set()
        self._suspicious_users: set[int] = set()

    def _get_key(self, prefix: str, identifier: str) -> str:
        """Generate Redis key."""
        return f"security:{prefix}:{identifier}"

    async def record_login_attempt(
        self,
        user_id: int | None,
        ip_address: str,
        success: bool,
        user_agent: str | None = None,
    ) -> None:
        """
        Record a login attempt.

        Args:
            user_id: User ID if known
            ip_address: Client IP address
            success: Whether login was successful
            user_agent: Client user agent string
        """
        event = SecurityEvent(
            event_type=(
                SecurityEventType.LOGIN_SUCCESS if success else SecurityEventType.LOGIN_FAILURE
            ),
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            ip_address=ip_address,
            details={"user_agent": user_agent or "unknown"},
        )

        # Track in memory
        self._login_attempts[ip_address].append(event)
        self._ip_events[ip_address].append(event)
        if user_id:
            self._user_activity[user_id].append(event)

        # Persist to Redis if available
        if self.redis:
            await self._persist_event(event)

        # Check for brute force
        if not success:
            is_brute_force = await self.detect_brute_force(ip_address)
            if is_brute_force:
                logger.warning(f"Brute force detected from IP: {ip_address}")
                await self._handle_brute_force(ip_address, user_id)

    async def detect_brute_force(self, ip_address: str) -> bool:
        """
        Detect brute force attacks from an IP.

        Returns:
            True if brute force detected
        """
        attempts = self._login_attempts[ip_address]
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.BRUTE_FORCE_WINDOW)

        # Count failed attempts in window
        recent_failures = sum(
            1
            for a in attempts
            if a.event_type == SecurityEventType.LOGIN_FAILURE and a.timestamp > cutoff
        )

        return recent_failures >= self.BRUTE_FORCE_THRESHOLD

    async def detect_suspicious_ip(self, ip_address: str) -> bool:
        """
        Detect if IP shows suspicious activity patterns.

        Returns:
            True if IP is suspicious
        """
        events = self._ip_events[ip_address]
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)

        # Count events in last hour
        recent_events = sum(1 for e in events if e.timestamp > cutoff)

        return recent_events >= self.SUSPICIOUS_IP_THRESHOLD

    async def detect_unusual_access_hours(self, user_id: int) -> bool:
        """
        Detect if user accesses system at unusual hours.

        Returns:
            True if unusual hours detected
        """
        current_hour = datetime.now(timezone.utc).hour
        if current_hour not in self.UNUSUAL_HOURS:
            return False

        # Check user's typical access pattern
        activity = self._user_activity[user_id]
        if len(activity) < 10:
            return False  # Not enough data

        # Calculate typical hours
        typical_hours = set()
        for event in list(activity)[:-10]:  # Exclude recent
            typical_hours.add(event.timestamp.hour)

        # If user never accessed during unusual hours before, flag it
        return current_hour not in typical_hours

    async def detect_privilege_escalation(self, user_id: int, requested_permission: str) -> bool:
        """
        Detect potential privilege escalation attempts.

        Returns:
            True if suspicious escalation detected
        """
        # Check if user has history of failed permission attempts
        activity = self._user_activity[user_id]

        recent_denials = sum(
            1
            for a in activity
            if a.event_type == SecurityEventType.PRIVILEGE_ESCALATION
            and a.timestamp > datetime.now(timezone.utc) - timedelta(hours=24)
        )

        return recent_denials >= 3

    async def record_security_event(
        self,
        event_type: SecurityEventType,
        user_id: int | None = None,
        ip_address: str | None = None,
        details: dict[str, str] | None = None,
        threat_level: ThreatLevel = ThreatLevel.LOW,
    ) -> None:
        """Record a generic security event."""
        event = SecurityEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            ip_address=ip_address,
            details=details or {},
            threat_level=threat_level,
        )

        # Track in memory
        if ip_address:
            self._ip_events[ip_address].append(event)
        if user_id:
            self._user_activity[user_id].append(event)

        # Persist to Redis
        if self.redis:
            await self._persist_event(event)

        # Log high-severity events
        if threat_level in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            logger.warning(
                f"High severity security event: {event_type.value} "
                f"from user={user_id} ip={ip_address}"
            )

    async def _persist_event(self, event: SecurityEvent) -> None:
        """Persist event to Redis."""
        if not self.redis:
            return

        event_data = {
            "type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "user_id": event.user_id,
            "ip_address": event.ip_address,
            "details": json.dumps(event.details),
            "threat_level": event.threat_level.value,
        }

        # Store in time-series
        key = f"security:events:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
        await self.redis.lpush(key, json.dumps(event_data))
        await self.redis.expire(key, 86400 * 30)  # Keep 30 days

    async def _handle_brute_force(self, ip_address: str, user_id: int | None) -> None:
        """Handle detected brute force attack."""
        self._blocked_ips.add(ip_address)

        event = SecurityEvent(
            event_type=SecurityEventType.BRUTE_FORCE_ATTEMPT,
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            ip_address=ip_address,
            threat_level=ThreatLevel.HIGH,
            details={"action": "ip_blocked"},
        )

        await self.record_security_event(
            event.event_type,
            event.user_id,
            event.ip_address,
            event.details,
            event.threat_level,
        )

        # TODO: Send alert to security team
        # TODO: Add IP to firewall blocklist

    def is_ip_blocked(self, ip_address: str) -> bool:
        """Check if IP is blocked."""
        return ip_address in self._blocked_ips

    async def get_threat_summary(
        self, hours: int = 24
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get summary of security threats.

        Returns: Dict[str, Any]ionary with threat statistics  # TODO(TYPE): replace Any with concrete type
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        summary: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "total_events": 0,
            "by_type": defaultdict(int),
            "by_threat_level": defaultdict(int),
            "blocked_ips": len(self._blocked_ips),
            "suspicious_users": len(self._suspicious_users),
            "top_offending_ips": [],
        }

        # Aggregate events
        for ip_events in self._ip_events.values():
            for event in ip_events:
                if event.timestamp > cutoff:
                    summary["total_events"] += 1
                    summary["by_type"][event.event_type.value] += 1
                    summary["by_threat_level"][event.threat_level.value] += 1

        # Get top offending IPs
        ip_counts: defaultdict[str, int] = defaultdict(int)
        for ip, events in self._ip_events.items():
            ip_counts[ip] = sum(1 for e in events if e.timestamp > cutoff)

        summary["top_offending_ips"] = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]

        return summary

    async def unblock_ip(self, ip_address: str) -> bool:
        """Unblock an IP address."""
        if ip_address in self._blocked_ips:
            self._blocked_ips.remove(ip_address)
            logger.info(f"IP unblocked: {ip_address}")
            return True
        return False


# Global instance
_security_monitor: SecurityMonitor | None = None


def get_security_monitor(redis_client: AsyncRedisClient | None = None) -> SecurityMonitor:
    """Get or create security monitor instance."""
    global _security_monitor
    if _security_monitor is None:
        _security_monitor = SecurityMonitor(redis_client)
    return _security_monitor
