"""SymbioticAgent Tests - 100% Happy & Unhappy Paths."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.als.agents.symbiotic_agent import SymbioticAgent
from src.core.als.infrastructure.signal_bus import Signal, SignalTier
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType

# =============================================================================
# Test Agent Implementation
# =============================================================================


class StubSymbioticAgent(SymbioticAgent):
    """Testable implementation of SymbioticAgent."""

    def __init__(self, tenant_id, signal_bus, **kwargs):
        super().__init__(
            agent_id="test_agent",
            agent_type=AgentType.GENERIC,
            tenant_id=tenant_id,
            signal_bus=signal_bus,
            department="test",
            **kwargs,
        )
        self.observe_called = False
        self.orient_called = False
        self.decide_called = False
        self.act_called = False

    async def observe(self, signal: Signal) -> dict:
        """Observe phase."""
        self.observe_called = True
        return {
            "source": signal.source_agent_id,
            "payload": signal.payload,
            "tier": signal.tier.value,
        }

    async def orient(self, observation: dict) -> dict:
        """Orient phase."""
        self.orient_called = True
        return {
            "analyzed": True,
            "source": observation["source"],
            "action_needed": observation["payload"].get("action", "unknown"),
        }

    async def decide(self, orientation: dict) -> str:
        """Decide phase."""
        self.decide_called = True
        return orientation.get("action_needed", "default_action")

    async def act(self, decision: str) -> ExecutionResult:
        """Act phase."""
        self.act_called = True
        return ExecutionResult(
            success=True, result_data={"executed": decision}, task_id="test_task"
        )

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Execute task - required by EnhancedBaseAgent."""
        return ExecutionResult(
            success=True, result_data={"task_executed": task.id}, task_id=task.id
        )


class FailingSymbioticAgent(SymbioticAgent):
    """Agent that fails for unhappy path tests."""

    def __init__(self, tenant_id, signal_bus, fail_at="act", **kwargs):
        super().__init__(
            agent_id="failing_agent",
            agent_type=AgentType.GENERIC,
            tenant_id=tenant_id,
            signal_bus=signal_bus,
            department="test",
            **kwargs,
        )
        self.fail_at = fail_at

    async def observe(self, signal: Signal) -> dict:
        if self.fail_at == "observe":
            raise Exception("Observe phase failed")
        return {"test": "observation"}

    async def orient(self, observation: dict) -> dict:
        if self.fail_at == "orient":
            raise Exception("Orient phase failed")
        return {"test": "orientation"}

    async def decide(self, orientation: dict) -> str:
        if self.fail_at == "decide":
            raise Exception("Decide phase failed")
        return "test_decision"

    async def act(self, decision: str) -> ExecutionResult:
        if self.fail_at == "act":
            raise Exception("Act phase failed")
        return ExecutionResult(success=True, result_data={})

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Execute task - required by EnhancedBaseAgent."""
        return ExecutionResult(
            success=True, result_data={"task_executed": task.id}, task_id=task.id
        )


# =============================================================================
# SymbioticAgent Happy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestSymbioticAgentHappyPaths:
    """Happy path tests for SymbioticAgent."""

    @pytest.fixture
    def mock_signal_bus(self):
        """Create mock SignalBus."""
        bus = MagicMock()
        bus.emit = AsyncMock(return_value="signal_id")
        bus.listen = AsyncMock()
        return bus

    async def test_agent_initialization(self, mock_signal_bus):
        """HAPPY: Initialize agent successfully."""
        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus)

        with patch.object(agent, "_register_with_organism", return_value=None):
            result = await agent.initialize()

            assert result is True
            assert agent.tenant_id == 10001
            assert agent.agent_id == "test_agent"

    async def test_ooda_loop_execution(self, mock_signal_bus):
        """HAPPY: Execute full OODA loop."""
        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus)

        signal = Signal(
            tenant_id=10001,
            source_agent_id="sender",
            target_agent_ids=["test_agent"],
            tier=SignalTier.COGNITIVE,
            payload={"action": "process_data"},
        )

        result = await agent.execute_ooda(signal)

        assert agent.observe_called is True
        assert agent.orient_called is True
        assert agent.decide_called is True
        assert agent.act_called is True
        assert result.success is True
        assert result.result_data["executed"] == "process_data"

    async def test_emit_signal(self, mock_signal_bus):
        """HAPPY: Emit signal to bus."""
        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus)

        signal_id = await agent.emit_signal(
            tier=SignalTier.COGNITIVE,
            payload={"result": "success"},
            target_agents=["orchestrator"],
        )

        assert signal_id is not None
        mock_signal_bus.emit.assert_called_once()

    async def test_query_agents(self, mock_signal_bus):
        """HAPPY: Query other agents."""
        mock_signal_bus.query = AsyncMock(
            return_value=[{"responder": "agent1", "payload": {"answer": "yes"}}]
        )

        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus)

        responses = await agent.query_agents(
            target_agents=["agent1", "agent2"],
            query_type="capability_check",
            payload={"capability": "analyze"},
            timeout_ms=1000,
        )

        assert len(responses) == 1
        assert responses[0]["responder"] == "agent1"

    async def test_get_load_default(self, mock_signal_bus):
        """HAPPY: Get default load (0.0)."""
        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus)

        load = agent._get_load()

        assert load == 0.0  # Default implementation


# =============================================================================
# SymbioticAgent Unhappy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestSymbioticAgentUnhappyPaths:
    """Unhappy path tests for SymbioticAgent."""

    @pytest.fixture
    def mock_signal_bus(self):
        """Create mock SignalBus."""
        bus = MagicMock()
        bus.emit = AsyncMock(return_value="signal_id")
        return bus

    async def test_ooda_observe_failure(self, mock_signal_bus):
        """UNHAPPY: OODA fails during observe phase."""
        agent = FailingSymbioticAgent(
            tenant_id=10001, signal_bus=mock_signal_bus, fail_at="observe"
        )

        signal = Signal(
            tenant_id=10001,
            source_agent_id="sender",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={},
        )

        result = await agent.execute_ooda(signal)

        assert result.success is False
        assert "Observe phase failed" in result.error_message

    async def test_ooda_orient_failure(self, mock_signal_bus):
        """UNHAPPY: OODA fails during orient phase."""
        agent = FailingSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus, fail_at="orient")

        signal = Signal(
            tenant_id=10001,
            source_agent_id="sender",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={},
        )

        result = await agent.execute_ooda(signal)

        assert result.success is False
        assert "Orient phase failed" in result.error_message

    async def test_ooda_decide_failure(self, mock_signal_bus):
        """UNHAPPY: OODA fails during decide phase."""
        agent = FailingSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus, fail_at="decide")

        signal = Signal(
            tenant_id=10001,
            source_agent_id="sender",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={},
        )

        result = await agent.execute_ooda(signal)

        assert result.success is False
        assert "Decide phase failed" in result.error_message

    async def test_ooda_act_failure(self, mock_signal_bus):
        """UNHAPPY: OODA fails during act phase."""
        agent = FailingSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus, fail_at="act")

        signal = Signal(
            tenant_id=10001,
            source_agent_id="sender",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={},
        )

        result = await agent.execute_ooda(signal)

        assert result.success is False
        assert "Act phase failed" in result.error_message

    async def test_initialization_failure(self, mock_signal_bus):
        """UNHAPPY: Initialization fails."""
        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=mock_signal_bus)

        with patch.object(agent, "_register_with_organism", side_effect=Exception("DB Error")):
            result = await agent.initialize()

            assert result is False


# =============================================================================
# Integration Tests (require real services)
# =============================================================================


@pytest.mark.integration
@pytest.mark.asyncio
class TestSymbioticAgentIntegration:
    """Integration tests with real services."""

    async def test_full_agent_lifecycle(self, signal_bus, db_session):
        """HAPPY: Full agent lifecycle with real services."""
        agent = StubSymbioticAgent(tenant_id=10001, signal_bus=signal_bus)

        # Initialize
        result = await agent.initialize()
        assert result is True

        # Process signal
        signal = Signal(
            tenant_id=10001,
            source_agent_id="test",
            target_agent_ids=["test_agent"],
            tier=SignalTier.COGNITIVE,
            payload={"action": "test"},
        )

        result = await agent.execute_ooda(signal)
        assert result.success is True

        # Shutdown
        await agent.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
