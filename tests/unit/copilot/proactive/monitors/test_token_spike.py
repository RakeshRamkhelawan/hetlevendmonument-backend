"""Unit tests for TokenSpikeMonitor."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.copilot.council.types import Severity
from src.core.copilot.proactive.monitors.token_spike import TokenSpikeMonitor


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


class FakePromClient:
    def __init__(
        self,
        sums: dict[str, float] | None = None,
        avgs: dict[str, float] | None = None,
    ) -> None:
        self._sums = sums or {}
        self._avgs = avgs or {}

    async def list_workflows(self, tenant_id: int) -> list[Any]:
        return []

    async def execution_count(self, workflow_id: str, tenant_id: int, since: str) -> int:
        return 0

    async def get_histogram_p95(
        self, metric_name: str, labels: dict[str, str], since: str
    ) -> float:
        return 0.0

    async def get_counter_sum(self, metric_name: str, labels: dict[str, str], since: str) -> float:
        key = labels.get("tenant_id", "")
        return self._sums.get(key, 0.0)

    async def get_counter_average(
        self, metric_name: str, labels: dict[str, str], window: str, bucket: str
    ) -> float:
        key = labels.get("tenant_id", "")
        return self._avgs.get(key, 0.0)


@pytest.mark.unit
class TestTokenSpikeMonitor:
    async def test_no_signal_when_under_min_tokens(self) -> None:
        prom = FakePromClient(sums={"1": 50000}, avgs={"1": 20000})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_emitted_on_spike(self) -> None:
        prom = FakePromClient(sums={"1": 500000}, avgs={"1": 200000})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH
        assert "2.5x" in signals[0].title

    async def test_no_signal_when_below_multiplier(self) -> None:
        prom = FakePromClient(sums={"1": 300000}, avgs={"1": 200000})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_no_signal_when_baseline_zero(self) -> None:
        prom = FakePromClient(sums={"1": 500000}, avgs={"1": 0})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_dedup_prevents_duplicate_signals_within_ttl(self) -> None:
        prom = FakePromClient(sums={"1": 500000}, avgs={"1": 200000})
        redis = FakeRedis()
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        signals2 = await monitor.detect(1)
        assert len(signals2) == 0

    async def test_dedup_allows_signal_after_ttl_expires(self) -> None:
        prom = FakePromClient(sums={"1": 500000}, avgs={"1": 200000})
        redis = FakeRedis()
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        redis._keys.clear()
        signals2 = await monitor.detect(1)
        assert len(signals2) == 1

    async def test_detection_reasoning_contains_values(self) -> None:
        prom = FakePromClient(sums={"1": 500000}, avgs={"1": 200000})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert "500,000" in signals[0].detection_reasoning
        assert "200,000" in signals[0].detection_reasoning
        assert "2.50x" in signals[0].detection_reasoning

    async def test_anti_noise_for_new_tenant(self) -> None:
        """New tenant with low token usage should not trigger."""
        prom = FakePromClient(sums={"1": 50000}, avgs={"1": 0})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_exactly_at_threshold(self) -> None:
        prom = FakePromClient(sums={"1": 400000}, avgs={"1": 200000})
        monitor = TokenSpikeMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1  # 2.0x >= SPIKE_MULTIPLIER
