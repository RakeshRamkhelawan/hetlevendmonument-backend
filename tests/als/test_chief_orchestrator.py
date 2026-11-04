"""Chief Orchestrator Tests - 100% Happy & Unhappy Paths."""

from datetime import datetime
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.core.als.agents.chief_orchestrator import (
    ChiefOrchestrator,
    OrchestratorMode,
    OrchestratorState,
    TaskAssignment,
)
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier
from src.core.shared.interfaces import ExecutionResult, TaskData

# =============================================================================
# Chief Orchestrator Happy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestChiefOrchestratorHappyPaths:
    """Happy path tests for ChiefOrchestrator."""

    @pytest.fixture
    def mock_signal_bus(self):
        """Create mock SignalBus."""
        bus = MagicMock(spec=SignalBus)
        bus.emit = AsyncMock(return_value="signal_id_123")
        bus.query = AsyncMock(
            return_value=[
                {"responder": "agent1", "payload": {"capable": True, "load": 0.5}},
                {"responder": "agent2", "payload": {"capable": True, "load": 0.3}},
            ]
        )
        bus.block_tenant = AsyncMock()
        bus.unblock_tenant = AsyncMock()
        return bus

    @pytest.fixture
    def orchestrator(self, mock_signal_bus):
        """Create ChiefOrchestrator instance."""
        return ChiefOrchestrator(
            tenant_id=10001, signal_bus=mock_signal_bus, agent_id="test_orchestrator"
        )

    async def test_initialization_success(self, orchestrator):
        """HAPPY: Initialize orchestrator successfully."""
        with patch.object(orchestrator, "_sync_agent_registry", return_value=None):
            result = await orchestrator.initialize()

            assert result is True
            assert orchestrator.tenant_id == 10001
            assert orchestrator.state.mode == OrchestratorMode.HYBRID

    async def test_delegate_task_success(self, orchestrator, mock_signal_bus):
        """HAPPY: Delegate task to agent successfully."""
        with patch.object(orchestrator, "_sync_agent_registry", return_value=None):
            await orchestrator.initialize()

        task = TaskData(
            id="task_001", title="Analysis Task", description="Analyze data", priority=5
        )

        result = await orchestrator.delegate_task(task)

        assert result.success is True
        assert result.task_id == "task_001"
        assert result.result_data is not None
        assert "assigned_agent" in result.result_data
        mock_signal_bus.emit.assert_called()

    async def test_delegate_task_with_preferred_agents(self, orchestrator, mock_signal_bus):
        """HAPPY: Delegate task to preferred agents."""
        with patch.object(orchestrator, "_sync_agent_registry", return_value=None):
            await orchestrator.initialize()

        task = TaskData(
            id="task_002",
            title="Code Generation",
            description="Generate Python code",
            priority=3,
        )

        result = await orchestrator.delegate_task(
            task=task, preferred_agents=["code_agent_1", "code_agent_2"]
        )

        assert result.success is True
        mock_signal_bus.query.assert_called_with(
            source_agent="test_orchestrator",
            target_agents=["code_agent_1", "code_agent_2"],
            query_type="capability_check",
            payload=ANY,
            timeout_ms=1000,
            tenant_id=10001,
        )

    async def test_broadcast_to_all_success(self, orchestrator, mock_signal_bus):
        """HAPPY: Broadcast message to all agents."""
        await orchestrator.initialize()

        signal_ids = await orchestrator.broadcast_to_all(
            message_type="system_announcement",
            payload={"message": "System maintenance in 5 minutes"},
        )

        assert len(signal_ids) > 0
        mock_signal_bus.emit.assert_called()

    async def test_get_system_health(self, orchestrator):
        """HAPPY: Get system health status."""
        await orchestrator.initialize()

        # Add some agents to state
        orchestrator.state.healthy_agents = {"agent1", "agent2", "agent3"}
        orchestrator.state.stressed_agents = {"agent4"}

        health = await orchestrator.get_system_health()

        assert health["tenant_id"] == 10001
        assert health["total_agents"] == 4
        assert health["healthy"] == 3
        assert health["stressed"] == 1
        assert health["health_percentage"] == 75.0

    async def test_shutdown_graceful(self, orchestrator):
        """HAPPY: Graceful shutdown."""
        await orchestrator.initialize()

        # Should not raise
        await orchestrator.shutdown()

        assert orchestrator._heartbeat_task is None


# =============================================================================
# Chief Orchestrator Unhappy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestChiefOrchestratorUnhappyPaths:
    """Unhappy path tests for ChiefOrchestrator."""

    @pytest.fixture
    def mock_signal_bus_empty_responses(self):
        """Mock SignalBus with empty responses (no agents available)."""
        bus = MagicMock(spec=SignalBus)
        bus.emit = AsyncMock(return_value="signal_id_123")
        bus.query = AsyncMock(return_value=[])  # No agents respond
        return bus

    async def test_delegate_task_no_agents_available(self, mock_signal_bus_empty_responses):
        """UNHAPPY: No agents available for task."""
        orchestrator = ChiefOrchestrator(
            tenant_id=10001, signal_bus=mock_signal_bus_empty_responses
        )
        with patch.object(orchestrator, "_sync_agent_registry", return_value=None):
            await orchestrator.initialize()

        task = TaskData(
            id="task_003",
            title="Rare Specialty",
            description="Special task",
            priority=5,
        )

        result = await orchestrator.delegate_task(task)

        assert result.success is False
        assert "No agents available" in result.error_message

    async def test_initialize_failure_db_error(self):
        """UNHAPPY: Initialization fails due to database error."""
        mock_bus = MagicMock(spec=SignalBus)
        orchestrator = ChiefOrchestrator(tenant_id=10001, signal_bus=mock_bus)

        with patch.object(orchestrator, "_sync_agent_registry", side_effect=Exception("DB Error")):
            result = await orchestrator.initialize()

            assert result is False

    @pytest.fixture
    def orchestrator(self, mock_signal_bus_empty_responses):
        """Create ChiefOrchestrator instance."""
        return ChiefOrchestrator(
            tenant_id=10001,
            signal_bus=mock_signal_bus_empty_responses,
            agent_id="test_orchestrator",
        )

    async def test_task_assignment_with_invalid_priority(self, orchestrator):
        """UNHAPPY: Task with invalid priority raises validation error."""
        with patch.object(orchestrator, "_sync_agent_registry", return_value=None):
            await orchestrator.initialize()

        # TaskPriority only allows 1, 3, 5, 9 - test with invalid value raises error
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TaskData(
                id="task_004",
                title="Test Task",
                description="Test with invalid priority",
                priority=0,  # Invalid - should raise
            )


# =============================================================================
# TaskAssignment Tests
# =============================================================================


class TestTaskAssignment:
    """Tests for TaskAssignment dataclass."""

    def test_task_assignment_creation(self):
        """HAPPY: Create task assignment."""
        assignment = TaskAssignment(
            task_id="task_001",
            assigned_agent="agent_1",
            agent_type="analyzer",
            priority=5,
            estimated_duration=300,
            dependencies=["task_000"],
        )

        assert assignment.task_id == "task_001"
        assert assignment.assigned_agent == "agent_1"
        assert assignment.status == "pending"  # Default

    def test_task_assignment_defaults(self):
        """HAPPY: Task assignment with defaults."""
        assignment = TaskAssignment(
            task_id="task_002",
            assigned_agent="agent_2",
            agent_type="code",
            priority=3,
            estimated_duration=600,
        )

        assert assignment.dependencies == []  # Default is empty list
        assert assignment.status == "pending"


# =============================================================================
# OrchestratorState Tests
# =============================================================================


class TestOrchestratorState:
    """Tests for OrchestratorState dataclass."""

    def test_state_initialization(self):
        """HAPPY: Initialize orchestrator state."""
        state = OrchestratorState(
            mode=OrchestratorMode.AUTONOMOUS,
            active_tasks={},
            completed_tasks=[],
            agent_load={},
            performance_metrics={},
            healthy_agents=set(),
            stressed_agents=set(),
        )

        assert state.mode == OrchestratorMode.AUTONOMOUS
        assert len(state.active_tasks) == 0
        assert len(state.healthy_agents) == 0

    def test_state_with_data(self):
        """HAPPY: State with actual data."""
        state = OrchestratorState(
            mode=OrchestratorMode.HYBRID,
            active_tasks={"task_1": TaskAssignment("task_1", "agent_1", "type", 5, 100)},
            completed_tasks=["task_0"],
            agent_load={"agent_1": 0.5, "agent_2": 0.8},
            performance_metrics={"avg_time": 120},
            healthy_agents={"agent_1", "agent_2"},
            stressed_agents={"agent_3"},
        )

        assert len(state.active_tasks) == 1
        assert len(state.healthy_agents) == 2
        assert len(state.stressed_agents) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
