"""Unit tests for AuditAnomalyMonitor."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.core.copilot.council.types import Severity
from src.core.copilot.proactive.monitors.audit_anomaly import AuditAnomalyMonitor


class FakeTenantRepo:
    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1


class FakeRedis:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True


class FakeAuditRepo:
    def __init__(self, counts: list[dict[str, Any]] | None = None) -> None:
        self._counts = counts or []

    async def count_permission_denied_per_user(
        self, tenant_id: int, hours: int
    ) -> list[dict[str, Any]]:
        return self._counts


class FakeRoleRepo:
    """Returns a configurable answer for was_any_role_created_after."""

    def __init__(self, role_created_recently: bool = False) -> None:
        self._role_created_recently = role_created_recently
        self.calls: list[tuple[int, datetime]] = []

    async def was_any_role_created_after(self, tenant_id: int, after: datetime) -> bool:
        self.calls.append((tenant_id, after))
        return self._role_created_recently


_ABOVE_THRESHOLD = [
    {"user_id": 1, "count": 3},
    {"user_id": 2, "count": 3},
    {"user_id": 3, "count": 5},
]


def _make_monitor(
    audit_counts: list[dict[str, Any]] | None = None,
    role_created_recently: bool = False,
    redis: FakeRedis | None = None,
) -> AuditAnomalyMonitor:
    return AuditAnomalyMonitor(
        None,
        None,
        FakeTenantRepo(),
        redis or FakeRedis(),
        FakeAuditRepo(audit_counts),
        FakeRoleRepo(role_created_recently),
    )


@pytest.mark.unit
class TestAuditAnomalyMonitor:
    async def test_no_signal_when_under_threshold(self) -> None:
        monitor = _make_monitor([{"user_id": 1, "count": 2}, {"user_id": 2, "count": 1}])
        assert await monitor.detect(1) == []

    async def test_signal_emitted_at_threshold(self) -> None:
        monitor = _make_monitor(_ABOVE_THRESHOLD)
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH
        assert "3 gebruikers" in signals[0].title

    async def test_no_signal_when_all_counts_zero(self) -> None:
        monitor = _make_monitor([])
        assert await monitor.detect(1) == []

    async def test_dedup_prevents_duplicate_signals(self) -> None:
        redis = FakeRedis()
        monitor = _make_monitor(_ABOVE_THRESHOLD, redis=redis)
        assert len(await monitor.detect(1)) == 1
        assert len(await monitor.detect(1)) == 0

    async def test_dedup_allows_after_ttl_expires(self) -> None:
        redis = FakeRedis()
        monitor = _make_monitor(_ABOVE_THRESHOLD, redis=redis)
        assert len(await monitor.detect(1)) == 1
        redis._keys.clear()
        assert len(await monitor.detect(1)) == 1

    async def test_detection_reasoning_contains_values(self) -> None:
        monitor = _make_monitor(_ABOVE_THRESHOLD)
        signals = await monitor.detect(1)
        assert "3 users" in signals[0].detection_reasoning
        assert "24h" in signals[0].detection_reasoning

    async def test_context_contains_totals(self) -> None:
        monitor = _make_monitor(_ABOVE_THRESHOLD)
        signals = await monitor.detect(1)
        assert signals[0].context["total_denied"] == 11
        assert signals[0].context["affected_user_count"] == 3

    async def test_interval_is_hourly(self) -> None:
        assert AuditAnomalyMonitor.interval_seconds == 3600

    async def test_affected_user_count_matches_unique_users(self) -> None:
        monitor = _make_monitor(
            [{"user_id": 1, "count": 10}, {"user_id": 2, "count": 5}, {"user_id": 3, "count": 3}]
        )
        signals = await monitor.detect(1)
        assert signals[0].context["affected_user_count"] == 3
        assert signals[0].context["total_denied"] == 18

    # -- Grace period tests --------------------------------------------------

    async def test_no_signal_when_role_created_recently(self) -> None:
        """Grace period: suppress anomaly if a role was created within 24h."""
        monitor = _make_monitor(_ABOVE_THRESHOLD, role_created_recently=True)
        assert await monitor.detect(1) == []

    async def test_signal_emitted_when_no_recent_role_creation(self) -> None:
        """No grace period active: anomaly signal must be emitted."""
        monitor = _make_monitor(_ABOVE_THRESHOLD, role_created_recently=False)
        assert len(await monitor.detect(1)) == 1

    async def test_grace_period_check_receives_correct_tenant(self) -> None:
        """role_repo must be called with the correct tenant_id."""
        role_repo = FakeRoleRepo(role_created_recently=False)
        monitor = AuditAnomalyMonitor(
            None, None, FakeTenantRepo(), FakeRedis(), FakeAuditRepo(_ABOVE_THRESHOLD), role_repo
        )
        await monitor.detect(tenant_id=7)
        assert role_repo.calls[0][0] == 7

    async def test_grace_period_cutoff_is_24h_ago(self) -> None:
        """Grace period cutoff must be exactly GRACE_PERIOD_HOURS in the past."""
        role_repo = FakeRoleRepo(role_created_recently=False)
        monitor = AuditAnomalyMonitor(
            None, None, FakeTenantRepo(), FakeRedis(), FakeAuditRepo(_ABOVE_THRESHOLD), role_repo
        )
        before = datetime.now(timezone.utc)
        await monitor.detect(1)
        after = datetime.now(timezone.utc)
        cutoff = role_repo.calls[0][1]
        assert before - timedelta(hours=AuditAnomalyMonitor.GRACE_PERIOD_HOURS) <= cutoff
        assert cutoff <= after - timedelta(
            hours=AuditAnomalyMonitor.GRACE_PERIOD_HOURS
        ) + timedelta(seconds=1)

    async def test_grace_period_constant_is_24(self) -> None:
        assert AuditAnomalyMonitor.GRACE_PERIOD_HOURS == 24

    async def test_context_includes_grace_period_hours(self) -> None:
        monitor = _make_monitor(_ABOVE_THRESHOLD)
        signals = await monitor.detect(1)
        assert signals[0].context["grace_period_hours"] == 24

    async def test_role_repo_failure_is_fail_open(self) -> None:
        """If role_repo raises, the signal is still emitted (fail-open) to avoid blind spots."""

        class BrokenRoleRepo:
            async def was_any_role_created_after(self, tenant_id: int, after: datetime) -> bool:
                raise RuntimeError("db unreachable")

        monitor = AuditAnomalyMonitor(
            None,
            None,
            FakeTenantRepo(),
            FakeRedis(),
            FakeAuditRepo(_ABOVE_THRESHOLD),
            BrokenRoleRepo(),  # type: ignore[arg-type]
        )
        signals = await monitor.detect(1)
        assert len(signals) == 1

    async def test_suggested_actions_include_snooze(self) -> None:
        monitor = _make_monitor(_ABOVE_THRESHOLD)
        signals = await monitor.detect(1)
        actions = [a["action"] for a in signals[0].suggested_actions]
        assert "snooze_signal" in actions

    async def test_tenant_isolation(self) -> None:
        """Signals for tenant 1 must not bleed into tenant 2 (dedup keys are tenant-scoped)."""
        redis = FakeRedis()
        monitor = _make_monitor(_ABOVE_THRESHOLD, redis=redis)
        signals_t1 = await monitor.detect(1)
        signals_t2 = await monitor.detect(2)
        assert len(signals_t1) == 1
        assert len(signals_t2) == 1
        assert signals_t1[0].tenant_id == 1
        assert signals_t2[0].tenant_id == 2
