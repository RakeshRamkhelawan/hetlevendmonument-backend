"""Integration test: all five platform monitors under ProactiveScheduler."""

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
from src.core.copilot.proactive.monitors import (
    AgentHealthMonitor,
    CircuitBreakerMonitor,
    QueueDepthMonitor,
    TokenSpikeMonitor,
    WorkflowLatencyMonitor,
)
from src.core.copilot.proactive.scheduler import ProactiveScheduler
from src.core.copilot.proactive.types import Signal


class FakeTenantRepo:
    async def list_active_ids(self) -> list[int]:
        return [1]

    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        return 42

    async def get_platform_admin_tenant_id(self) -> int:
        return 1

    async def get_tenant_id_for_user(self, user_id: int) -> int | None:  # noqa: ARG002
        return 1

    async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None:  # noqa: ARG002
        return 1


class FakeRedis:
    def __init__(self) -> None:
        self._keys: set[str] = set()
        self._depths: dict[str, int] = {}

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int = 0) -> Any:
        if nx and key in self._keys:
            return None
        self._keys.add(key)
        return True

    async def llen(self, key: str) -> int:
        return self._depths.get(key, 0)


class FakePromClient:
    async def list_workflows(self, tenant_id: int) -> list[Any]:
        return []

    async def execution_count(self, workflow_id: str, tenant_id: int, since: str) -> int:
        return 0

    async def get_histogram_p95(
        self, metric_name: str, labels: dict[str, str], since: str
    ) -> float:
        return 0.0

    async def get_counter_sum(self, metric_name: str, labels: dict[str, str], since: str) -> float:
        return 0.0

    async def get_counter_average(
        self, metric_name: str, labels: dict[str, str], window: str, bucket: str
    ) -> float:
        return 0.0


class FakeFailover:
    async def get_circuit_states(self) -> dict[str, str]:
        return {}


@pytest.fixture
def mock_scheduler() -> Any:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    sched = MagicMock(spec=AsyncIOScheduler)
    sched.add_job = MagicMock()
    return sched


@pytest.mark.integration
class TestAllMonitorsRegister:
    def test_all_five_monitors_register_under_scheduler(self, mock_scheduler: Any) -> None:
        repo = FakeTenantRepo()
        redis = FakeRedis()
        prom = FakePromClient()
        failover = FakeFailover()

        monitors = [
            AgentHealthMonitor(None, None, MagicMock(), repo, redis),
            WorkflowLatencyMonitor(None, None, prom, repo, redis),
            QueueDepthMonitor(None, None, repo, redis, ["default"]),
            TokenSpikeMonitor(None, None, prom, repo, redis),
            CircuitBreakerMonitor(None, None, failover, repo, redis),
        ]

        ps = ProactiveScheduler(mock_scheduler, repo, monitors)
        ps.start()

        assert mock_scheduler.add_job.call_count == 5
        job_ids = {call.kwargs["id"] for call in mock_scheduler.add_job.call_args_list}
        expected = {
            "monitor:agent_health",
            "monitor:workflow_latency",
            "monitor:queue_depth",
            "monitor:token_spike",
            "monitor:circuit_breaker",
        }
        assert job_ids == expected

    @pytest.mark.asyncio
    async def test_scheduler_runs_all_monitors_without_errors(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        repo = FakeTenantRepo()
        redis = FakeRedis()
        prom = FakePromClient()
        failover = FakeFailover()

        monitors = [
            AgentHealthMonitor(None, None, MagicMock(), repo, redis),
            WorkflowLatencyMonitor(None, None, prom, repo, redis),
            QueueDepthMonitor(None, None, repo, redis, ["default"]),
            TokenSpikeMonitor(None, None, prom, repo, redis),
            CircuitBreakerMonitor(None, None, failover, repo, redis),
        ]

        # Use a real scheduler but don't start it; we run manually
        sched = AsyncIOScheduler()
        ps = ProactiveScheduler(sched, repo, monitors)

        # Manually run each monitor for tenant 1
        for monitor in monitors:
            await ps._run_for_all_tenants(monitor)

        # No shutdown needed since scheduler was never started
