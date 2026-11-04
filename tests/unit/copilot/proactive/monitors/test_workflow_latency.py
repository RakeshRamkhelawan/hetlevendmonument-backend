"""Unit tests for WorkflowLatencyMonitor."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.copilot.council.types import DataClassification, Severity
from src.core.copilot.proactive.monitors.workflow_latency import WorkflowLatencyMonitor
from src.core.copilot.proactive.types import Signal


class FakeTenantRepo:
    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1


class FakeRedis:
    def __init__(self, existing_keys: set[str] | None = None) -> None:
        self._keys = existing_keys or set()

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True


class FakeWorkflow:
    def __init__(self, wf_id: str, name: str) -> None:
        self.id = wf_id
        self.name = name


class FakePromClient:
    def __init__(
        self,
        workflows: list[FakeWorkflow] | None = None,
        exec_counts: dict[str, int] | None = None,
        p95_values: dict[str, float] | None = None,
        baseline_values: dict[str, float] | None = None,
    ) -> None:
        self._workflows = workflows or []
        self._exec_counts = exec_counts or {}
        self._p95 = p95_values or {}
        self._baseline = baseline_values or {}

    async def list_workflows(self, tenant_id: int) -> list[FakeWorkflow]:
        return self._workflows

    async def execution_count(self, workflow_id: str, tenant_id: int, since: str) -> int:
        return self._exec_counts.get(workflow_id, 0)

    async def get_histogram_p95(
        self, metric_name: str, labels: dict[str, str], since: str
    ) -> float:
        wf_id = labels.get("workflow_id", "")
        if since == "1d":
            return self._p95.get(wf_id, 0.0)
        return self._baseline.get(wf_id, 0.0)

    async def get_counter_sum(self, metric_name: str, labels: dict[str, str], since: str) -> float:
        return 0.0

    async def get_counter_average(
        self, metric_name: str, labels: dict[str, str], window: str, bucket: str
    ) -> float:
        return 0.0


@pytest.mark.unit
class TestWorkflowLatencyMonitor:
    async def test_no_signal_when_under_threshold(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "Test Workflow")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 1.0},
            baseline_values={"wf1": 1.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_emitted_when_threshold_exceeded(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "Test Workflow")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 1.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert len(signals) == 1
        assert signals[0].severity == Severity.HIGH
        assert "3.0x" in signals[0].title or "10.0x" in signals[0].title

    async def test_no_signal_when_below_min_executions(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "Test Workflow")],
            exec_counts={"wf1": 5},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 1.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []

    async def test_signal_severity_high_above_5x(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "W")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 1.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals[0].severity == Severity.HIGH

    async def test_signal_severity_medium_between_3x_and_5x(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "W")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 4.0},
            baseline_values={"wf1": 1.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals[0].severity == Severity.MEDIUM

    async def test_dedup_prevents_duplicate_signals_within_ttl(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "W")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 1.0},
        )
        redis = FakeRedis()
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        signals2 = await monitor.detect(1)
        assert len(signals2) == 0

    async def test_dedup_allows_signal_after_ttl_expires(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "W")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 1.0},
        )
        redis = FakeRedis()
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), redis)
        signals1 = await monitor.detect(1)
        assert len(signals1) == 1
        redis._keys.clear()
        signals2 = await monitor.detect(1)
        assert len(signals2) == 1

    async def test_detection_reasoning_contains_threshold_and_value(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "W")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 1.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert "10.00x" in signals[0].detection_reasoning
        assert "3.0x" in signals[0].detection_reasoning
        assert "20" in signals[0].detection_reasoning

    async def test_no_signal_when_baseline_is_zero(self) -> None:
        prom = FakePromClient(
            workflows=[FakeWorkflow("wf1", "W")],
            exec_counts={"wf1": 20},
            p95_values={"wf1": 10.0},
            baseline_values={"wf1": 0.0},
        )
        monitor = WorkflowLatencyMonitor(None, None, prom, FakeTenantRepo(), FakeRedis())
        signals = await monitor.detect(1)
        assert signals == []
