"""
F4 tests: AgentHealthMonitorAgent wires SelfHealingSystem callback.

TDD RED phase. These tests verify that when AgentHealthMonitorAgent detects
CRITICAL or STALE agent-status transitions, it invokes SelfHealingSystem.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.agent_health_monitor_agent import AgentHealthMonitorAgent, HealthStatus
from src.core.autonomy.self_healing_system import RepairResult, SelfHealingSystem


def _run(coro):  # type: ignore[no-untyped-def]
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_result() -> RepairResult:
    return RepairResult(
        repair_id="r_test",
        failure_id="f_test",
        success=True,
        actions_taken=["verify_health"],
        healing_time=timedelta(seconds=1),
        final_status="completed",
    )


def _mock_healing() -> MagicMock:
    healing = MagicMock(spec=SelfHealingSystem)
    healing.detect_and_diagnose_failure = AsyncMock(return_value=MagicMock())
    healing.execute_repair_plan = AsyncMock(return_value=_make_result())
    return healing


class TestF4HealthMonitorHealingWiring:
    def test_default_healing_system_is_none(self) -> None:
        """No healing system registered by default."""
        monitor = AgentHealthMonitorAgent(agent_id="mon_default", tenant_id=1)
        assert monitor._healing_system is None

    def test_set_healing_system_stores_reference(self) -> None:
        """set_healing_system stores the reference on the monitor."""
        monitor = AgentHealthMonitorAgent(agent_id="mon_set", tenant_id=1)
        healing = SelfHealingSystem()
        monitor.set_healing_system(healing)
        assert monitor._healing_system is healing

    def test_critical_agent_triggers_healing(self) -> None:
        """When agent enters CRITICAL status, SelfHealingSystem is invoked."""
        monitor = AgentHealthMonitorAgent(agent_id="mon_crit", tenant_id=1)
        healing = _mock_healing()
        monitor.set_healing_system(healing)

        async def _drive() -> None:
            # 50 failed tasks -> CRITICAL (high error_rate + low success_rate = 2 issues)
            for _ in range(50):
                await monitor.record("agent_x", "worker", 1000.0, False, batch=False)
            await monitor._check_all()
            await asyncio.sleep(0.15)  # allow fire-and-forget task to complete

        _run(_drive())
        healing.detect_and_diagnose_failure.assert_called_once()

    def test_stale_agent_triggers_healing(self) -> None:
        """A STALE agent (heartbeat timeout exceeded) triggers SelfHealingSystem."""
        monitor = AgentHealthMonitorAgent(
            agent_id="mon_stale",
            tenant_id=1,
            thresholds={"heartbeat_timeout_s": 0},  # threshold=0 -> any age is stale
        )
        healing = _mock_healing()
        monitor.set_healing_system(healing)

        async def _drive() -> None:
            await monitor.record("agent_stale", "worker", 100.0, True, batch=False)
            await asyncio.sleep(0.05)  # ensure heartbeat age > 0s threshold
            await monitor._check_all()
            await asyncio.sleep(0.15)

        _run(_drive())
        healing.detect_and_diagnose_failure.assert_called_once()

    def test_warning_does_not_trigger_healing(self) -> None:
        """WARNING status (1 metric breach) does NOT invoke SelfHealingSystem."""
        monitor = AgentHealthMonitorAgent(agent_id="mon_warn", tenant_id=1)
        healing = _mock_healing()
        monitor.set_healing_system(healing)

        async def _drive() -> None:
            # High latency only (6000 ms > 5000 threshold) = 1 issue -> WARNING
            # success_rate=1.0 and error_rate=0.0 remain within threshold
            for _ in range(10):
                await monitor.record("agent_warn", "worker", 6000.0, True, batch=False)
            await monitor._check_all()
            await asyncio.sleep(0.15)

        _run(_drive())
        healing.detect_and_diagnose_failure.assert_not_called()

    def test_healing_fires_only_on_transition(self) -> None:
        """Healing fires once on CRITICAL transition; subsequent checks don't re-trigger."""
        monitor = AgentHealthMonitorAgent(agent_id="mon_trans", tenant_id=1)
        healing = _mock_healing()
        monitor.set_healing_system(healing)

        async def _drive() -> None:
            for _ in range(50):
                await monitor.record("agent_t", "worker", 1000.0, False, batch=False)
            # First check: UNKNOWN->CRITICAL transition -> healing fires
            await monitor._check_all()
            await asyncio.sleep(0.15)
            # Second check: still CRITICAL, no new transition -> no additional healing
            await monitor._check_all()
            await asyncio.sleep(0.15)

        _run(_drive())
        # Called exactly once across both _check_all runs
        assert healing.detect_and_diagnose_failure.call_count == 1

    def test_no_healing_system_no_exception(self) -> None:
        """Without a registered healing system, CRITICAL detection is silent."""
        monitor = AgentHealthMonitorAgent(agent_id="mon_noheal", tenant_id=1)

        async def _drive() -> None:
            for _ in range(50):
                await monitor.record("agent_nx", "worker", 1000.0, False, batch=False)
            await monitor._check_all()
            await asyncio.sleep(0.15)

        # Should not raise
        _run(_drive())
