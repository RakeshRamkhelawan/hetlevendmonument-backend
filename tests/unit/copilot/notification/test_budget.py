"""
Unit tests for Notification Budget Tracker.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.copilot.notification.budget import BudgetVerdict, NotificationBudgetTracker
from src.core.copilot.notification.models import NotificationPreferences


@pytest.fixture
def mock_redis() -> AsyncMock:
    mock = AsyncMock()
    # By default, mock redis.eval to increment starting from 0 to 1, etc.
    # We will track internal state for simple atomic incr mock
    state: dict[str, int] = {}

    async def mock_eval(
        script: str, numkeys: int, key: str, ttl: int, limit: int
    ) -> int:
        val = state.get(key, 0) + 1
        if val > limit:
            # Lua script rolls back the increment
            return -1
        state[key] = val
        return val

    mock.eval.side_effect = mock_eval

    mock._state = state

    # We remove register_script to trigger eval fallback for simple mock logic
    del mock.register_script
    return mock


@pytest.mark.unit
async def test_consume_first_notification_returns_approved(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, daily_limit=5)

    result = await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")

    assert result.verdict == BudgetVerdict.APPROVED
    assert result.remaining == 4
    assert result.reason == "WITHIN_BUDGET"


@pytest.mark.unit
async def test_consume_within_limit_decrements_remaining(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, daily_limit=5)

    # mock state to simulate 3 already consumed
    mock_redis._state["copilot:notif:1:1:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")] = 3

    result = await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")

    assert result.verdict == BudgetVerdict.APPROVED
    assert result.remaining == 1


@pytest.mark.unit
async def test_consume_at_limit_returns_deferred(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, daily_limit=5)

    mock_redis._state["copilot:notif:1:1:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")] = 5

    result = await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")

    assert result.verdict == BudgetVerdict.DEFERRED
    assert result.remaining == 0
    assert result.reason == "DAILY_LIMIT_REACHED"


@pytest.mark.unit
async def test_consume_at_limit_does_not_consume_budget(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, daily_limit=5)

    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"copilot:notif:1:1:{date_key}"
    mock_redis._state[key] = 5

    await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")

    # Should still be 5 — Lua script rolled back atomically inside eval
    assert mock_redis._state[key] == 5
    # No separate DECR call needed with atomic Lua script
    mock_redis.decr.assert_not_called()


@pytest.mark.unit
async def test_critical_severity_bypasses_limit_with_override(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(
        user_id=1, tenant_id=1, daily_limit=5, critical_always_immediate=True
    )

    mock_redis._state["copilot:notif:1:1:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")] = 10

    result = await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="critical")

    assert result.verdict == BudgetVerdict.OVERRIDE
    assert result.reason == "CRITICAL_BYPASS"
    assert not mock_redis.eval.called


@pytest.mark.unit
async def test_individual_delivery_mode_returns_approved(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, delivery_mode="individual")

    result = await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")
    assert result.verdict == BudgetVerdict.APPROVED


@pytest.mark.unit
async def test_quiet_hours_defers_non_critical(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, quiet_hours_start=22, quiet_hours_end=7)

    now = datetime(2026, 5, 23, 23, 0, 0, tzinfo=timezone.utc)

    result = await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=now)

    assert result.verdict == BudgetVerdict.DEFERRED
    assert result.reason == "QUIET_HOURS"


@pytest.mark.unit
async def test_quiet_hours_does_not_block_critical(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(
        user_id=1,
        tenant_id=1,
        quiet_hours_start=22,
        quiet_hours_end=7,
        critical_always_immediate=True,
    )

    now = datetime(2026, 5, 23, 23, 0, 0, tzinfo=timezone.utc)

    result = await tracker.consume(
        tenant_id=1, user_id=1, prefs=prefs, severity="critical", now=now
    )

    assert result.verdict == BudgetVerdict.OVERRIDE


@pytest.mark.unit
async def test_quiet_hours_uses_user_timezone_amsterdam(mock_redis: AsyncMock) -> None:
    """Regression test voor audit-bevinding #2 (sprint 1+2 ADR-027 audit, 2026-05-23):
    quiet_hours_timezone moet de stille uren shiften naar lokale tijd, niet UTC.

    Stelling:
    - User in Europe/Amsterdam met quiet hours 22:00-07:00 lokaal.
    - In juli is CEST (UTC+2): 21:00 UTC == 23:00 lokaal -> binnen quiet hours.
    - 06:00 UTC == 08:00 lokaal -> buiten quiet hours.

    Zonder de timezone-koppeling zou de tracker UTC-uren gebruiken en op het
    verkeerde moment stilte afdwingen voor non-UTC gebruikers.
    """
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(
        user_id=1,
        tenant_id=1,
        quiet_hours_start=22,
        quiet_hours_end=7,
        quiet_hours_timezone="Europe/Amsterdam",
    )

    # 21:00 UTC in juli = 23:00 CEST -> in lokale quiet hours
    in_quiet = datetime(2026, 7, 15, 21, 0, 0, tzinfo=timezone.utc)
    result_in = await tracker.consume(
        tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=in_quiet
    )
    assert result_in.verdict == BudgetVerdict.DEFERRED
    assert result_in.reason == "QUIET_HOURS"

    # 06:00 UTC in juli = 08:00 CEST -> buiten lokale quiet hours
    out_of_quiet = datetime(2026, 7, 15, 6, 0, 0, tzinfo=timezone.utc)
    result_out = await tracker.consume(
        tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=out_of_quiet
    )
    assert result_out.verdict == BudgetVerdict.APPROVED


@pytest.mark.unit
async def test_quiet_hours_timezone_default_is_utc(mock_redis: AsyncMock) -> None:
    """Regression test voor audit-bevinding #2: bij None timezone fallback naar UTC.

    Bevestigt dat een NotificationPreferences zonder quiet_hours_timezone identiek
    werkt aan een instantie met quiet_hours_timezone='UTC' (backward compatibility
    voor bestaande prefs-rijen die de nieuwe kolom nog niet hebben).
    """
    tracker = NotificationBudgetTracker(mock_redis)
    prefs_none = NotificationPreferences(
        user_id=1, tenant_id=1, quiet_hours_start=22, quiet_hours_end=7
    )
    prefs_utc = NotificationPreferences(
        user_id=2,
        tenant_id=1,
        quiet_hours_start=22,
        quiet_hours_end=7,
        quiet_hours_timezone="UTC",
    )

    # 23:00 UTC: beide moeten DEFER opleveren
    now = datetime(2026, 5, 23, 23, 0, 0, tzinfo=timezone.utc)

    r_none = await tracker.consume(
        tenant_id=1, user_id=1, prefs=prefs_none, severity="normal", now=now
    )
    r_utc = await tracker.consume(
        tenant_id=1, user_id=2, prefs=prefs_utc, severity="normal", now=now
    )

    assert r_none.verdict == BudgetVerdict.DEFERRED
    assert r_utc.verdict == BudgetVerdict.DEFERRED
    assert r_none.reason == r_utc.reason == "QUIET_HOURS"


@pytest.mark.unit
async def test_cross_midnight_quiet_hours(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, quiet_hours_start=22, quiet_hours_end=7)

    now1 = datetime(2026, 5, 23, 23, 0, 0, tzinfo=timezone.utc)
    now2 = datetime(2026, 5, 23, 3, 0, 0, tzinfo=timezone.utc)
    now3 = datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)

    assert (
        await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=now1)
    ).verdict == BudgetVerdict.DEFERRED
    assert (
        await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=now2)
    ).verdict == BudgetVerdict.DEFERRED
    assert (
        await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=now3)
    ).verdict == BudgetVerdict.APPROVED


@pytest.mark.unit
@pytest.mark.security
async def test_redis_key_isolates_tenants(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1)

    await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")
    await tracker.consume(tenant_id=2, user_id=1, prefs=prefs, severity="normal")

    keys = list(mock_redis._state.keys())
    assert any(":1:1:" in key for key in keys)
    assert any(":2:1:" in key for key in keys)


@pytest.mark.unit
@pytest.mark.security
async def test_redis_key_isolates_users(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1)

    await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal")
    await tracker.consume(tenant_id=1, user_id=2, prefs=prefs, severity="normal")

    keys = list(mock_redis._state.keys())
    assert any(":1:1:" in key for key in keys)
    assert any(":1:2:" in key for key in keys)


@pytest.mark.unit
async def test_counter_resets_at_utc_midnight(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1)

    now_before = datetime(2026, 5, 23, 23, 59, 0, tzinfo=timezone.utc)
    now_after = datetime(2026, 5, 24, 0, 1, 0, tzinfo=timezone.utc)

    await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=now_before)
    await tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal", now=now_after)

    keys = list(mock_redis._state.keys())
    assert len(keys) == 2
    assert any("2026-05-23" in key for key in keys)
    assert any("2026-05-24" in key for key in keys)


@pytest.mark.unit
async def test_concurrent_consume_safe(mock_redis: AsyncMock) -> None:
    tracker = NotificationBudgetTracker(mock_redis)
    prefs = NotificationPreferences(user_id=1, tenant_id=1, daily_limit=25)

    # We will simulate 50 concurrent calls
    # With our mock state tracker it works sequentially under asyncio.gather but
    # tests the python logic correctly handling the values.

    coros = [
        tracker.consume(tenant_id=1, user_id=1, prefs=prefs, severity="normal") for _ in range(50)
    ]
    results = await asyncio.gather(*coros)

    approved = [r for r in results if r.verdict == BudgetVerdict.APPROVED]
    deferred = [r for r in results if r.verdict == BudgetVerdict.DEFERRED]

    assert len(approved) == 25
    assert len(deferred) == 25
