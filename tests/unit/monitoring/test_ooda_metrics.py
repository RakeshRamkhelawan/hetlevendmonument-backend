"""Tests for OODA Metrics tracking."""

from datetime import datetime

import pytest

from src.core.monitoring.ooda_metrics import OODAMetrics, OODAPhase, PhaseTiming


class TestOODAMetricsHappyPath:
    """Happy path tests for OODA metrics."""

    @pytest.fixture
    def metrics(self):
        return OODAMetrics()

    @pytest.mark.asyncio
    async def test_start_and_end_phase(self, metrics):
        """Should track phase timing correctly."""
        await metrics.start_phase(
            execution_id="exec_001",
            agent_id="agent_001",
            phase=OODAPhase.OBSERVE,
            tenant_id="tenant_123",
        )

        duration = await metrics.end_phase(
            execution_id="exec_001", phase=OODAPhase.OBSERVE, success=True
        )

        assert duration is not None
        assert duration >= 0

    @pytest.mark.asyncio
    async def test_complete_ooda_cycle(self, metrics):
        """Should track complete OODA cycle."""
        execution_id = "exec_002"
        agent_id = "agent_001"
        tenant_id = "tenant_123"

        # Complete all 4 phases
        for phase in [OODAPhase.OBSERVE, OODAPhase.ORIENT, OODAPhase.DECIDE, OODAPhase.ACT]:
            await metrics.start_phase(execution_id, agent_id, phase, tenant_id)
            duration = await metrics.end_phase(execution_id, phase, success=True)
            assert duration is not None

    @pytest.mark.asyncio
    async def test_get_execution_summary(self, metrics):
        """Should return execution summary."""
        execution_id = "exec_003"
        agent_id = "agent_001"
        tenant_id = "tenant_123"

        # Run a cycle
        for phase in [OODAPhase.OBSERVE, OODAPhase.ORIENT]:
            await metrics.start_phase(execution_id, agent_id, phase, tenant_id)
            await metrics.end_phase(execution_id, phase, success=True)

        summary = await metrics.get_execution_summary(execution_id)

        assert summary is not None
        assert summary["execution_id"] == execution_id
        assert summary["phases_completed"] == 2
        assert summary["all_phases_successful"] is True

    @pytest.mark.asyncio
    async def test_phase_with_metadata(self, metrics):
        """Should store metadata with phase."""
        execution_id = "exec_004"

        await metrics.start_phase(
            execution_id=execution_id,
            agent_id="agent_001",
            phase=OODAPhase.OBSERVE,
            tenant_id="tenant_123",
            metadata={"data_source": "api", "records": 100},
        )

        await metrics.end_phase(
            execution_id=execution_id,
            phase=OODAPhase.OBSERVE,
            success=True,
            metadata={"processed": 100},
        )

        summary = await metrics.get_execution_summary(execution_id)
        assert summary is not None


class TestOODAMetricsUnhappyPath:
    """Unhappy path tests for OODA metrics."""

    @pytest.fixture
    def metrics(self):
        return OODAMetrics()

    @pytest.mark.asyncio
    async def test_end_phase_without_start(self, metrics):
        """Should handle ending phase that wasn't started."""
        duration = await metrics.end_phase(
            execution_id="exec_unknown", phase=OODAPhase.OBSERVE, success=True
        )

        assert duration is None

    @pytest.mark.asyncio
    async def test_failed_phase_tracking(self, metrics):
        """Should track failed phases."""
        execution_id = "exec_fail"
        agent_id = "agent_001"
        tenant_id = "tenant_123"

        await metrics.start_phase(execution_id, agent_id, OODAPhase.ORIENT, tenant_id)
        await metrics.end_phase(execution_id, OODAPhase.ORIENT, success=False)

        summary = await metrics.get_execution_summary(execution_id)

        assert summary is not None
        assert summary["all_phases_successful"] is False

    @pytest.mark.asyncio
    async def test_get_summary_for_unknown_execution(self, metrics):
        """Should return None for unknown execution."""
        summary = await metrics.get_execution_summary("unknown_exec")

        assert summary is None


class TestOODAAverages:
    """Tests for average calculations."""

    @pytest.fixture
    def metrics(self):
        return OODAMetrics()

    @pytest.mark.asyncio
    async def test_get_average_cycle_time(self, metrics):
        """Should calculate average cycle times."""
        agent_id = "agent_avg"
        tenant_id = "tenant_123"

        # Add some phase data
        for i in range(3):
            exec_id = f"exec_avg_{i}"
            await metrics.start_phase(exec_id, agent_id, OODAPhase.OBSERVE, tenant_id)
            await metrics.end_phase(exec_id, OODAPhase.OBSERVE, success=True)

        averages = await metrics.get_average_cycle_time(agent_id, tenant_id)

        assert "observe" in averages
        assert averages["observe"]["count"] == 3
        assert averages["observe"]["avg_ms"] >= 0
