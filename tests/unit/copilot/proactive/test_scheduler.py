"""Unit tests for ProactiveScheduler."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    Severity,
)
from src.core.copilot.proactive.monitor import ProactiveMonitor
from src.core.copilot.proactive.scheduler import ProactiveScheduler
from src.core.copilot.proactive.types import Signal


class FakeTenantRepo:
    def __init__(self, tenant_ids: list[int]) -> None:
        self._ids = tenant_ids

    async def list_active_ids(self) -> list[int]:
        return self._ids


class FailingMonitor(ProactiveMonitor):
    name = "failing"
    interval_seconds = 60

    async def detect(self, tenant_id: int) -> list[Signal]:
        raise RuntimeError("boom")


class SlowMonitor(ProactiveMonitor):
    name = "slow"
    interval_seconds = 10

    async def detect(self, tenant_id: int) -> list[Signal]:
        import asyncio

        await asyncio.sleep(100)
        return []


class OkMonitor(ProactiveMonitor):
    name = "ok"
    interval_seconds = 60

    def __init__(
        self,
        copilot_service: Any,
        dispatcher: Any,
        signals: list[Signal] | None = None,
    ) -> None:
        super().__init__(copilot_service, dispatcher)
        self._signals = signals or []
        self.detected_tenants: list[int] = []

    async def detect(self, tenant_id: int) -> list[Signal]:
        self.detected_tenants.append(tenant_id)
        return [s for s in self._signals if s.tenant_id == tenant_id]


class EventDrivenMonitor(ProactiveMonitor):
    name = "event_driven"
    interval_seconds = 0

    async def detect(self, tenant_id: int) -> list[Signal]:
        return []


@pytest.fixture
def mock_scheduler() -> Any:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    sched = MagicMock(spec=AsyncIOScheduler)
    sched.add_job = MagicMock()
    return sched


@pytest.mark.unit
class TestSchedulerRegistration:
    def test_scheduler_adds_job_per_monitor(self, mock_scheduler: Any) -> None:
        monitor = OkMonitor(None, None)
        repo = FakeTenantRepo([1])
        ps = ProactiveScheduler(mock_scheduler, repo, [monitor])
        ps.start()

        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args
        assert call_args.kwargs["id"] == "monitor:ok"
        assert call_args.kwargs["max_instances"] == 1
        assert call_args.kwargs["coalesce"] is True
        assert call_args.kwargs["replace_existing"] is True
        mock_scheduler.start.assert_called_once()

    def test_scheduler_skips_event_driven_monitor(self, mock_scheduler: Any) -> None:
        monitor = EventDrivenMonitor(None, None)
        repo = FakeTenantRepo([1])
        ps = ProactiveScheduler(mock_scheduler, repo, [monitor])
        ps.start()

        mock_scheduler.add_job.assert_not_called()

    def test_scheduler_shutdown(self, mock_scheduler: Any) -> None:
        repo = FakeTenantRepo([1])
        ps = ProactiveScheduler(mock_scheduler, repo, [])
        ps.shutdown(wait=False)
        mock_scheduler.shutdown.assert_called_once_with(wait=False)


@pytest.mark.unit
class TestSchedulerExecution:
    @pytest.mark.asyncio
    async def test_scheduler_runs_each_monitor_per_tenant(self) -> None:
        repo = FakeTenantRepo([1, 2])
        monitor = OkMonitor(None, None)
        ps = ProactiveScheduler(MagicMock(), repo, [monitor])

        await ps._run_for_all_tenants(monitor)
        assert monitor.detected_tenants == [1, 2]

    @pytest.mark.asyncio
    async def test_scheduler_one_tenant_crash_does_not_block_others(self) -> None:
        repo = FakeTenantRepo([1, 2])

        class CrashOnTenant(ProactiveMonitor):
            name = "crash"
            interval_seconds = 60

            async def detect(self, tenant_id: int) -> list[Signal]:
                if tenant_id == 1:
                    raise RuntimeError("boom")
                return []

        monitor = CrashOnTenant(None, None)
        ps = ProactiveScheduler(MagicMock(), repo, [monitor])

        # Should not raise
        await ps._run_for_all_tenants(monitor)

    @pytest.mark.asyncio
    async def test_scheduler_timeout_on_slow_detect(self) -> None:
        repo = FakeTenantRepo([1])
        monitor = SlowMonitor(None, None)
        ps = ProactiveScheduler(MagicMock(), repo, [monitor])

        # Should not raise; asyncio.wait_for raises TimeoutError which is caught
        await ps._run_for_all_tenants(monitor)

    @pytest.mark.asyncio
    async def test_scheduler_proposes_signals(self) -> None:
        signal = Signal(
            tenant_id=1,
            affected_user_id=1,
            monitor_name="ok",
            title="t",
            body="b",
            severity=Severity.LOW,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        decision = CouncilDecision(
            proposal_id=signal.signal_id,
            tenant_id=1,
            user_id=1,
            verdict=DecisionVerdict.APPROVED,
            officer_verdicts=(),
            explanation_for_user="ok",
            decision_hash="abc",
            previous_decision_hash=None,
            deliberation_ms=10,
        )
        mock_service = AsyncMock()
        mock_service.submit_proactive_proposal.return_value = decision
        mock_dispatcher = AsyncMock()

        monitor = OkMonitor(mock_service, mock_dispatcher, [signal])
        repo = FakeTenantRepo([1])
        ps = ProactiveScheduler(MagicMock(), repo, [monitor])

        await ps._run_for_all_tenants(monitor)

        mock_service.submit_proactive_proposal.assert_awaited_once()
        mock_dispatcher.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scheduler_does_not_dispatch_blocked_decision(self) -> None:
        signal = Signal(
            tenant_id=1,
            affected_user_id=1,
            monitor_name="ok",
            title="t",
            body="b",
            severity=Severity.LOW,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        decision = CouncilDecision(
            proposal_id=signal.signal_id,
            tenant_id=1,
            user_id=1,
            verdict=DecisionVerdict.BLOCKED,
            officer_verdicts=(),
            explanation_for_user="blocked",
            decision_hash="abc",
            previous_decision_hash=None,
            deliberation_ms=10,
        )
        mock_service = AsyncMock()
        mock_service.submit_proactive_proposal.return_value = decision
        mock_dispatcher = AsyncMock()

        monitor = OkMonitor(mock_service, mock_dispatcher, [signal])
        repo = FakeTenantRepo([1])
        ps = ProactiveScheduler(MagicMock(), repo, [monitor])

        await ps._run_for_all_tenants(monitor)

        mock_service.submit_proactive_proposal.assert_awaited_once()
        mock_dispatcher.dispatch.assert_not_awaited()


@pytest.mark.unit
class TestMockMonitor:
    @pytest.mark.asyncio
    async def test_mock_monitor_filters_by_tenant_id(self) -> None:
        s1 = Signal(
            tenant_id=1,
            affected_user_id=1,
            monitor_name="m",
            title="t1",
            body="b1",
            severity=Severity.LOW,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        s2 = Signal(
            tenant_id=2,
            affected_user_id=1,
            monitor_name="m",
            title="t2",
            body="b2",
            severity=Severity.LOW,
            data_classification=DataClassification.INTERNAL,
            suggested_actions=[],
            detection_reasoning="r",
            confidence=0.5,
            context={},
        )
        from src.core.copilot.proactive.monitors.mock import MockMonitor

        monitor = MockMonitor(None, None, [s1, s2])
        result = await monitor.detect(1)
        assert result == [s1]
