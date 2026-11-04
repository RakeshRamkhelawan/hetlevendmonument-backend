"""Unit tests for QueueDepthMonitor."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.copilot.council.types import Severity
from src.core.copilot.proactive.monitors.queue_depth import QueueDepthMonitor


class FakeTenantRepo:
    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1


class FakeRedis:
    def __init__(self, depths: dict[str, int] | None = None) -> None:
        self._depths = depths or {}
        self._keys: set[str] = set()

    async def llen(self, key: str) -> int:
        return self._depths.get(key, 0)

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True


@pytest.mark.unit
class TestQueueDepthMonitor:
    async def test_no_signal_when_under_threshold(self) -> None:
        redis = FakeRedis({"dramatiq:default": 500})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_medium_at_1500(self) -> None:
        redis = FakeRedis({"dramatiq:default": 1500})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.MEDIUM

    async def test_signal_high_at_6000(self) -> None:
        redis = FakeRedis({"dramatiq:default": 6000})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH

    async def test_signal_critical_at_12000(self) -> None:
        redis = FakeRedis({"dramatiq:default": 12000})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.CRITICAL

    async def test_dedup_prevents_duplicate_signals_within_ttl(self) -> None:
        redis = FakeRedis({"dramatiq:default": 1500})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        signals2 = await monitor.detect(1)
        assert len(signals2) == 0

    async def test_dedup_allows_signal_after_ttl_expires(self) -> None:
        redis = FakeRedis({"dramatiq:default": 1500})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        redis._keys.clear()
        signals2 = await monitor.detect(1)
        assert len(signals2) == 1

    async def test_multiple_queues(self) -> None:
        redis = FakeRedis({"dramatiq:q1": 1500, "dramatiq:q2": 6000})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["q1", "q2"])
        signals = await monitor.detect(1)
        assert len(signals) == 2
        severities = {s.context["queue"]: s.severity for s in signals}
        assert severities["q1"] == Severity.MEDIUM
        assert severities["q2"] == Severity.HIGH

    async def test_explicit_queue_names_no_wildcards(self) -> None:
        redis = FakeRedis({"dramatiq:default": 1500, "dramatiq:other": 3000})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].context["queue"] == "default"

    async def test_detection_reasoning_contains_values(self) -> None:
        redis = FakeRedis({"dramatiq:default": 1500})
        monitor = QueueDepthMonitor(None, None, FakeTenantRepo(), redis, ["default"])
        signals = await monitor.detect(1)
        assert "1500" in signals[0].detection_reasoning
        assert "1000" in signals[0].detection_reasoning
        assert "medium" in signals[0].detection_reasoning
