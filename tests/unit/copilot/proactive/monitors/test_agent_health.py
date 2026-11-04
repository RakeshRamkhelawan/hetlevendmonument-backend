"""Unit tests for AgentHealthMonitor."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.als.health_monitor import (
    ERROR_RATE_CRITICAL,
    HealthMetrics,
    HealthMonitorService,
    HealthStatus,
)
from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitors.agent_health import AgentHealthMonitor
from src.core.copilot.proactive.types import Signal


class FakeTenantRepo:
    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1


class FakeRedis:
    def __init__(self, existing_keys: set[str] | None = None) -> None:
        self._keys = existing_keys or set()
        self.calls: list[tuple[str, ...]] = []

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        self.calls.append((key, value, nx, ex))
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True


class FakeHealthRegistry:
    def __init__(self, service: HealthMonitorService | None = None) -> None:
        self._service = service

    def get_for_tenant(self, tenant_id: int) -> HealthMonitorService | None:
        return self._service


def _make_metrics(
    agent_id: str = "agent-1",
    error_rate: float = 0.0,
    error_count: int = 0,
    total_tasks: int = 10,
) -> HealthMetrics:
    return HealthMetrics(
        agent_id=agent_id,
        total_tasks=total_tasks,
        success_count=total_tasks - error_count,
        error_count=error_count,
        avg_latency_ms=100.0,
        error_rate=error_rate,
        success_rate=1.0 - error_rate,
        status=HealthStatus.HEALTHY,
        consecutive_failures=0,
    )


@pytest.mark.unit
class TestAgentHealthMonitor:
    async def test_no_signal_when_under_threshold(self) -> None:
        service = HealthMonitorService()
        service.record(MagicMock(agent_id="a1", tenant_id=1, success=True, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_emitted_when_threshold_exceeded(self) -> None:
        service = HealthMonitorService()
        # 30 errors out of 50 = 60% error rate
        for _ in range(20):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=True, latency_ms=10))
        for _ in range(30):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].title == "Agent a1 faalt 30x"
        assert signals[0].severity == Severity.HIGH
        assert signals[0].affected_user_id == 42

    async def test_signal_severity_scales_with_magnitude(self) -> None:
        service = HealthMonitorService()
        # 25 errors = exactly at HIGH threshold
        for _ in range(25):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=True, latency_ms=10))
        for _ in range(25):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH  # 25 >= HIGH_FAILURE_COUNT_THRESHOLD

    async def test_signal_medium_for_low_error_count(self) -> None:
        service = HealthMonitorService()
        # 5 errors out of 10 = 50% but only 5 errors
        for _ in range(5):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=True, latency_ms=10))
        for _ in range(5):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.MEDIUM  # 5 < 25

    async def test_signal_carries_tenant_admin_as_recipient(self) -> None:
        service = HealthMonitorService()
        for _ in range(25):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals[0].affected_user_id == 42

    async def test_detection_reasoning_explains_why(self) -> None:
        """OP-171 (2026-08-27) matcht ook losse percentages als fabricated-stat; deze tekst
        gaat ongewijzigd door naar de SanityOfficer via Proposal.reasoning en zou een echte
        (niet-gehallucineerde) meting daardoor laten blokkeren. Aantallen i.p.v. percentages."""
        service = HealthMonitorService()
        for _ in range(30):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert ERROR_RATE_CRITICAL == 0.5
        assert "30/30" in signals[0].detection_reasoning
        assert "%" not in signals[0].detection_reasoning

    async def test_dedup_prevents_duplicate_signals_within_ttl(self) -> None:
        service = HealthMonitorService()
        for _ in range(30):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        redis = FakeRedis()
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        # second call should be deduped
        signals2 = await monitor.detect(1)
        assert len(signals2) == 0

    async def test_dedup_allows_signal_after_ttl_expires(self) -> None:
        service = HealthMonitorService()
        for _ in range(30):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        redis = FakeRedis()
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        # Manually clear the dedup key to simulate TTL expiry
        redis._keys.clear()
        signals2 = await monitor.detect(1)
        assert len(signals2) == 1

    async def test_no_service_returns_empty(self) -> None:
        registry = FakeHealthRegistry(None)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_tenant_repo_called_once_per_detect(self) -> None:
        service = HealthMonitorService()
        for _ in range(30):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        for _ in range(30):
            service.record(MagicMock(agent_id="a2", tenant_id=1, success=False, latency_ms=10))
        registry = FakeHealthRegistry(service)
        repo = FakeTenantRepo()
        call_count = 0
        original = repo.get_primary_admin_user_id

        async def counting_get(tenant_id: int) -> int:
            nonlocal call_count
            call_count += 1
            return await original(tenant_id)

        repo.get_primary_admin_user_id = counting_get  # type: ignore[method-assign]
        monitor = AgentHealthMonitor(None, None, registry, repo, FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 2
        assert call_count == 1  # no N+1

    async def test_no_signal_for_healthy_agents(self) -> None:
        service = HealthMonitorService()
        for _ in range(50):
            service.record(MagicMock(agent_id="a1", tenant_id=1, success=True, latency_ms=10))
        registry = FakeHealthRegistry(service)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_cross_tenant_isolation(self) -> None:
        """Monitor for tenant A must not see agents of tenant B."""
        service_a = HealthMonitorService()
        for _ in range(30):
            service_a.record(MagicMock(agent_id="a1", tenant_id=1, success=False, latency_ms=10))
        # tenant B has healthy agent
        service_b = HealthMonitorService()
        for _ in range(50):
            service_b.record(MagicMock(agent_id="b1", tenant_id=2, success=True, latency_ms=10))

        registry = FakeHealthRegistry(service_a)
        monitor = AgentHealthMonitor(None, None, registry, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].context["agent_id"] == "a1"
