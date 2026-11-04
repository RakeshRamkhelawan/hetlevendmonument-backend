"""
Notification Budget Tracker implementation for Co-Pilot system.

Provides an atomic Redis-based budget tracker.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from src.core.copilot.notification.models import NotificationPreferences

logger = logging.getLogger(__name__)


class BudgetVerdict(str, Enum):
    APPROVED = "APPROVED"
    DEFERRED = "DEFERRED"
    OVERRIDE = "OVERRIDE"  # critical bypass


@dataclass(frozen=True, slots=True)
class BudgetResult:
    verdict: BudgetVerdict
    remaining: int
    daily_limit: int
    reason: str


# Atomic Lua script: INCR + EXPIRE + limit-check + rollback if over limit.
# Single round-trip - eliminates race between INCR and DECR (H-1).
LUA_INCR_WITH_LIMIT = """
local key = KEYS[1]
local ttl = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local val = redis.call('INCR', key)
if val == 1 then
    redis.call('EXPIRE', key, ttl)
end
if val > limit then
    redis.call('DECR', key)
    return -1
end
return val
"""


class NotificationBudgetTracker:
    """Atomic budget tracker bovenop Redis."""

    KEY_TEMPLATE = "copilot:notif:{tenant_id}:{user_id}:{date_key}"
    TTL_SECONDS = 25 * 3600  # 25h zodat midnight rollover gegarandeerd is

    def __init__(self, redis_client: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        self._redis = redis_client

        # Load Lua script on initialization if redis client supports it
        # Try to register it, fallback to eval if register is not available
        self._script = None
        if hasattr(self._redis, "register_script"):
            self._script = self._redis.register_script(LUA_INCR_WITH_LIMIT)

    def _in_quiet_hours(self, now: datetime, prefs: NotificationPreferences) -> bool:
        """Check if current time is within user's quiet hours.

        Converts to user's timezone so quiet hours work locally
        (prevents +/-1h misfires for CET/CEST users - M-5).
        """
        if prefs.quiet_hours_start is None or prefs.quiet_hours_end is None:
            return False

        from zoneinfo import ZoneInfo

        tz = ZoneInfo(prefs.quiet_hours_timezone or "UTC")
        local_now = now.astimezone(tz)
        hour = local_now.hour
        start, end = prefs.quiet_hours_start, prefs.quiet_hours_end
        if start < end:
            return start <= hour < end

        # cross-midnight
        return hour >= start or hour < end

    async def _atomic_incr_with_limit(self, key: str, ttl: int, limit: int) -> int:
        """Atomically increment, set TTL, and rollback if over limit."""
        if self._script:
            return int(await self._script(keys=[key], args=[ttl, limit]))
        else:
            return int(await self._redis.eval(LUA_INCR_WITH_LIMIT, 1, key, ttl, limit))

    async def consume(
        self,
        *,
        tenant_id: int,
        user_id: int,
        prefs: NotificationPreferences,
        severity: str,
        now: datetime | None = None,
    ) -> BudgetResult:
        now = now or datetime.now(timezone.utc)
        date_key = now.strftime("%Y-%m-%d")
        key = self.KEY_TEMPLATE.format(
            tenant_id=tenant_id,
            user_id=user_id,
            date_key=date_key,
        )

        # Critical bypass
        if severity == "critical" and prefs.critical_always_immediate:
            return BudgetResult(
                verdict=BudgetVerdict.OVERRIDE,
                remaining=-1,
                daily_limit=prefs.daily_limit,
                reason="CRITICAL_BYPASS",
            )

        # Quiet hours check (non-critical)
        if self._in_quiet_hours(now, prefs) and severity != "critical":
            return BudgetResult(
                verdict=BudgetVerdict.DEFERRED,
                remaining=-1,
                daily_limit=prefs.daily_limit,
                reason="QUIET_HOURS",
            )

        # Atomic INCR + EXPIRE + limit-check + rollback in single Lua script.
        new_value = await self._atomic_incr_with_limit(
            key, self.TTL_SECONDS, prefs.daily_limit
        )

        if new_value == -1:
            # Lua script rolled back because limit was exceeded
            return BudgetResult(
                verdict=BudgetVerdict.DEFERRED,
                remaining=0,
                daily_limit=prefs.daily_limit,
                reason="DAILY_LIMIT_REACHED",
            )

        return BudgetResult(
            verdict=BudgetVerdict.APPROVED,
            remaining=prefs.daily_limit - new_value,
            daily_limit=prefs.daily_limit,
            reason="WITHIN_BUDGET",
        )
