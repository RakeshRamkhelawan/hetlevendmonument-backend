"""Tests for OODA Metrics memory limit fix."""

import pytest

from src.core.monitoring.ooda_metrics import OODAMetrics, OODAPhase


class TestOODAMemoryLimit:
    """Test that OODA metrics enforces memory limits."""

    @pytest.fixture
    def metrics(self):
        return OODAMetrics()

    @pytest.mark.asyncio
    async def test_memory_limit_enforced(self, metrics):
        """Should enforce memory limit and rotate history."""
        # Set small limit for testing
        metrics._MAX_HISTORY_SIZE = 10

        # Add more events than the limit
        for i in range(15):
            await metrics.start_phase(
                execution_id=f"exec_{i}",
                agent_id="agent_001",
                phase=OODAPhase.OBSERVE,
                tenant_id="tenant_123",
            )
            await metrics.end_phase(f"exec_{i}", OODAPhase.OBSERVE, success=True)

        # Should have rotated and kept only half
        assert len(metrics._execution_history) <= 10

    @pytest.mark.asyncio
    async def test_memory_rotation_keeps_recent(self, metrics):
        """Should keep most recent events after rotation."""
        metrics._MAX_HISTORY_SIZE = 6

        # Add events
        for i in range(10):
            await metrics.start_phase(
                execution_id=f"exec_{i:02d}",  # Pad with zeros for sorting
                agent_id="agent_001",
                phase=OODAPhase.OBSERVE,
                tenant_id="tenant_123",
            )
            await metrics.end_phase(f"exec_{i:02d}", OODAPhase.OBSERVE, success=True)

        # Recent events should be present
        recent_exec_ids = [r["execution_id"] for r in metrics._execution_history[-3:]]
        assert (
            "exec_07" in recent_exec_ids
            or "exec_08" in recent_exec_ids
            or "exec_09" in recent_exec_ids
        )

    @pytest.mark.asyncio
    async def test_memory_limit_configurable(self, metrics):
        """Should allow configurable memory limit."""
        # Test different limits
        for limit in [5, 20, 100]:
            metrics.clear_history()
            metrics._MAX_HISTORY_SIZE = limit

            for i in range(limit + 5):
                await metrics.start_phase(
                    execution_id=f"exec_{i}",
                    agent_id="agent_001",
                    phase=OODAPhase.OBSERVE,
                    tenant_id="tenant_123",
                )
                await metrics.end_phase(f"exec_{i}", OODAPhase.OBSERVE, success=True)

            assert len(metrics._execution_history) <= limit

    def test_default_memory_limit_reasonable(self, metrics):
        """Should have reasonable default memory limit."""
        # Default should be set
        assert hasattr(metrics, "_MAX_HISTORY_SIZE")
        # Default should be at least 1000
        assert metrics._MAX_HISTORY_SIZE >= 1000
