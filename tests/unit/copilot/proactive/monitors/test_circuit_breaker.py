"""Unit tests for CircuitBreakerMonitor."""

from __future__ import annotations

from typing import Any

import pytest

from src.core.copilot.council.types import Severity
from src.core.copilot.proactive.monitors.circuit_breaker import CircuitBreakerMonitor


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


class FakeFailoverProvider:
    def __init__(self, states: dict[str, str]) -> None:
        self._states = states

    async def get_circuit_states(self) -> dict[str, str]:
        return self._states


@pytest.mark.unit
class TestCircuitBreakerMonitor:
    async def test_no_signal_when_all_breakers_closed(self) -> None:
        provider = FakeFailoverProvider({"X#0": "closed", "Y#1": "closed"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_when_primary_provider_open(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open", "Y#1": "closed"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH
        assert "X" in signals[0].title

    async def test_signal_when_backup_provider_open(self) -> None:
        provider = FakeFailoverProvider({"X#0": "closed", "Y#1": "open"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.MEDIUM
        assert "Y" in signals[0].title

    async def test_no_signal_for_non_admin_tenant(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(2)  # tenant 2 != platform admin (1)
        assert signals == []

    async def test_reset_circuit_action_present(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        actions = signals[0].suggested_actions
        reset_actions = [a for a in actions if a.get("action") == "reset_circuit"]
        assert len(reset_actions) == 1
        assert reset_actions[0]["params"]["breaker_key"] == "X#0"

    async def test_dedup_global_prevents_duplicate(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open"})
        redis = FakeRedis()
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        signals2 = await monitor.detect(1)
        assert len(signals2) == 0

    async def test_dedup_allows_after_ttl(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open"})
        redis = FakeRedis()
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        redis._keys.clear()
        signals2 = await monitor.detect(1)
        assert len(signals2) == 1

    async def test_multiple_open_breakers(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open", "Y#1": "open"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 2
        severities = {s.context["breaker_key"]: s.severity for s in signals}
        assert severities["X#0"] == Severity.HIGH
        assert severities["Y#1"] == Severity.MEDIUM

    async def test_context_contains_is_primary(self) -> None:
        provider = FakeFailoverProvider({"X#0": "open"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals[0].context["is_primary"] is True

    async def test_half_open_does_not_trigger(self) -> None:
        provider = FakeFailoverProvider({"X#0": "half_open"})
        monitor = CircuitBreakerMonitor(None, None, provider, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []
