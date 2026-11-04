"""Smoke test: all 10 proactive monitors instantiate and register under ProactiveScheduler.

Sprint 5 delivers 10 monitors: 5 platform (interval-based) + 5 compliance
(4 interval-based + 2 event-driven). The scheduler skips event-driven monitors
(interval_seconds=0) to prevent IntervalTrigger(seconds=0) ValueError.
Expected: 8 scheduled jobs (DSARExportMonitor + PolicyChangeMonitor are skipped).
"""

from __future__ import annotations

from typing import Any

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.core.copilot.proactive.monitors import (
    AgentHealthMonitor,
    AuditAnomalyMonitor,
    CircuitBreakerMonitor,
    ConsentExpiryMonitor,
    DSARExportMonitor,
    PolicyChangeMonitor,
    QueueDepthMonitor,
    SensitiveWorkflowMonitor,
    TokenSpikeMonitor,
    WorkflowLatencyMonitor,
)
from src.core.copilot.proactive.scheduler import ProactiveScheduler


@pytest.mark.integration
@pytest.mark.als
async def test_all_10_monitors_register_under_scheduler(
    mock_copilot_service: Any,
    mock_dispatcher: Any,
    mock_tenant_repo: Any,
    real_redis_client: Any,
    mock_health_registry: Any,
    mock_prom: Any,
    mock_failover_provider: Any,
    mock_workflow_repo: Any,
    mock_pii_scanner: Any,
    mock_dpia_repo: Any,
    mock_event_bus: Any,
    mock_audit_repo: Any,
    mock_role_repo: Any,
    mock_consent_repo: Any,
) -> None:
    """All 10 monitors instantiate; 8 register under scheduler (2 event-driven skipped)."""
    monitors: list[Any] = [
        # 5 platform monitors (interval-based)
        AgentHealthMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_health_registry,
            mock_tenant_repo,
            real_redis_client,
        ),
        WorkflowLatencyMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_prom,
            mock_tenant_repo,
            real_redis_client,
        ),
        QueueDepthMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_tenant_repo,
            real_redis_client,
            queue_names=["default"],
        ),
        TokenSpikeMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_prom,
            mock_tenant_repo,
            real_redis_client,
        ),
        CircuitBreakerMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_failover_provider,
            mock_tenant_repo,
            real_redis_client,
        ),
        # 5 compliance monitors (4 interval + 2 event-driven)
        DSARExportMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_tenant_repo,
            real_redis_client,
            mock_event_bus,
        ),
        SensitiveWorkflowMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_tenant_repo,
            real_redis_client,
            mock_workflow_repo,
            mock_pii_scanner,
            mock_dpia_repo,
        ),
        AuditAnomalyMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_tenant_repo,
            real_redis_client,
            mock_audit_repo,
            mock_role_repo,
        ),
        PolicyChangeMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_tenant_repo,
            real_redis_client,
            mock_event_bus,
        ),
        ConsentExpiryMonitor(
            mock_copilot_service,
            mock_dispatcher,
            mock_tenant_repo,
            real_redis_client,
            mock_consent_repo,
        ),
    ]

    assert len(monitors) == 10, "Sprint 5 delivers exactly 10 monitors"

    event_driven = [m for m in monitors if m.interval_seconds <= 0]
    assert len(event_driven) == 2, (
        f"Expected 2 event-driven monitors, got {[m.name for m in event_driven]}"
    )
    assert {m.name for m in event_driven} == {"dsar_export", "policy_change"}

    scheduler = ProactiveScheduler(
        scheduler=AsyncIOScheduler(),
        tenant_repo=mock_tenant_repo,
        monitors=monitors,
    )
    scheduler.start()
    try:
        jobs = scheduler._scheduler.get_jobs()
        job_ids = {j.id for j in jobs}

        assert len(jobs) == 8, (
            f"Expected 8 scheduled jobs (2 event-driven skipped), "
            f"got {len(jobs)}: {sorted(job_ids)}"
        )
        for monitor in monitors:
            if monitor.interval_seconds > 0:
                expected_id = f"monitor:{monitor.name}"
                assert expected_id in job_ids, (
                    f"Job '{expected_id}' missing. Available: {sorted(job_ids)}"
                )
    finally:
        scheduler.shutdown(wait=False)
