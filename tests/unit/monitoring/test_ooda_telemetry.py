import time

import pytest

from src.core.monitoring.ooda_metrics import OODAMonitor
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_ooda_phase_tracking():
    monitor = OODAMonitor()
    agent_id = "test_agent"
    tenant_id = 1

    # Track a full cycle
    with monitor.track_phase(agent_id, tenant_id, "observe"):
        time.sleep(0.01)

    with monitor.track_phase(agent_id, tenant_id, "orient"):
        time.sleep(0.02)

    metrics = monitor.get_agent_metrics(agent_id, tenant_id)
    assert "observe" in metrics
    assert "orient" in metrics
    assert metrics["observe"] > 0
    assert metrics["orient"] > metrics["observe"]


def test_monitor_fails_gracefully_without_ids():
    monitor = OODAMonitor()
    # Should not raise exception
    with monitor.track_phase(None, None, "act"):
        pass
