"""
Integration tests for execution path adapters (Phase A3).

Verifies that all 6 execution paths correctly route through the unified gateway
with proper governance enforcement.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.agent_registry import AgentRegistry
from src.core.agents.gateway_adapters import (
    CVAStateMachineAdapter,
    DramatiqWorkflowAdapter,
    EnhancedBaseAgentAdapter,
    GatewayAdapterRegistry,
    OrchestratorAdapter,
    SubAgentFactoryAdapter,
    WebSocketLangGraphAdapter,
)
from src.core.agents.unified_gateway import UnifiedAgentGateway, UnifiedAgentGatewayConfig
from src.core.ethics.ethics_gate import EthicsEvaluation, EthicsGate, EthicsLevel
from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightGate, OversightResult
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import TaskPriority, TaskStatus


@pytest.fixture
def mock_registry():
    """Create mock agent registry."""
    registry = AsyncMock(spec=AgentRegistry)
    registry.get_agent_by_id = AsyncMock(
        return_value={
            "agent_id": "test_agent",
            "name": "Test Agent",
            "department": "testing",
            "specialisation": "test",
            "capabilities": ["testing"],
        }
    )
    return registry


@pytest.fixture
def mock_ethics_gate():
    """Create mock ethics gate."""
    gate = AsyncMock(spec=EthicsGate)
    evaluation = EthicsEvaluation(
        level=EthicsLevel.SAFE,
        score=100.0,
        concerns=[],
        recommendations=["Proceed"],
        category_scores={},
        timestamp=datetime.now(timezone.utc),
    )
    gate.evaluate = AsyncMock(return_value=evaluation)
    return gate


@pytest.fixture
def mock_oversight_gate():
    """Create mock oversight gate."""
    gate = AsyncMock(spec=OversightGate)
    result = OversightResult(
        allowed=True,
        requires_human_approval=False,
        risk_level=AIActRiskLevel.MINIMAL,
        reason="Permitted",
    )
    gate.check = AsyncMock(return_value=result)
    return gate


@pytest.fixture
def unified_gateway(mock_registry, mock_ethics_gate, mock_oversight_gate):
    """Create unified gateway with mocked dependencies."""
    return UnifiedAgentGateway(
        registry=mock_registry,
        ethics_gate=mock_ethics_gate,
        oversight_gate=mock_oversight_gate,
        config=UnifiedAgentGatewayConfig(
            enable_ethics_gate=True,
            enable_oversight_gate=True,
            enable_authority_check=True,
            enable_circuit_breaker=True,
            default_timeout_seconds=10.0,
        ),
    )


class TestExecutionPathAdapters:
    """Test all 6 execution path adapters."""

    def test_all_adapters_registered(self, unified_gateway):
        """Test that all 6 adapters are properly registered."""
        registry = GatewayAdapterRegistry(unified_gateway)

        assert len(registry.adapters) == 6
        assert "enhanced_base_agent" in registry.adapters
        assert "orchestrator" in registry.adapters
        assert "cva_state_machine" in registry.adapters
        assert "dramatiq_workflow" in registry.adapters
        assert "subagent_factory" in registry.adapters
        assert "websocket_langgraph" in registry.adapters

    def test_adapter_registry_status(self, unified_gateway):
        """Test gateway status includes all adapters."""
        registry = GatewayAdapterRegistry(unified_gateway)
        status = registry.get_gateway_status()

        assert status["adapters_registered"] == 6
        assert len(status["adapter_paths"]) == 6
        assert status["config"]["enable_ethics_gate"] is True
        assert status["config"]["enable_oversight_gate"] is True

    def test_get_adapter_by_key(self, unified_gateway):
        """Test getting specific adapter by key."""
        registry = GatewayAdapterRegistry(unified_gateway)

        adapter = registry.get_adapter("enhanced_base_agent")
        assert adapter is not None
        assert isinstance(adapter, EnhancedBaseAgentAdapter)

    def test_get_nonexistent_adapter(self, unified_gateway):
        """Test getting nonexistent adapter returns None."""
        registry = GatewayAdapterRegistry(unified_gateway)

        adapter = registry.get_adapter("nonexistent")
        assert adapter is None


class TestAdapterExecution:
    """Test adapter execution through unified gateway."""

    @pytest.mark.asyncio
    async def test_enhanced_base_agent_adapter_execution(self, unified_gateway):
        """Test EnhancedBaseAgent adapter routes through gateway."""
        adapter = EnhancedBaseAgentAdapter(unified_gateway)
        task = TaskData(
            title="Test Task",
            description="Test description",
            priority=TaskPriority.MEDIUM,
            status=TaskStatus.PENDING,
            agent_id="test_agent",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"status": "success"})

        result = await adapter.execute(task, executor)

        assert result.success is True
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_orchestrator_adapter_execution(self, unified_gateway):
        """Test Orchestrator adapter routes through gateway."""
        adapter = OrchestratorAdapter(unified_gateway)
        task = TaskData(
            title="Orchestrate workflow",
            description="Multi-agent orchestration",
            agent_id="orchestrator",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"result": "orchestrated"})

        result = await adapter.execute(task, executor)

        assert result.success is True
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_cva_adapter_execution(self, unified_gateway):
        """Test CVA State Machine adapter routes through gateway."""
        adapter = CVAStateMachineAdapter(unified_gateway)
        task = TaskData(
            title="CVA state transition",
            description="Conversational voice agent query",
            agent_id="cva",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"response": "Hello!"})

        result = await adapter.execute(task, executor)

        assert result.success is True
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_dramatiq_adapter_execution(self, unified_gateway):
        """Test Dramatiq Workflow adapter routes through gateway."""
        adapter = DramatiqWorkflowAdapter(unified_gateway)
        task = TaskData(
            title="Background job",
            description="Async background task",
            agent_id="worker",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"job_id": "123"})

        result = await adapter.execute(task, executor)

        assert result.success is True
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_subagent_factory_adapter_execution(self, unified_gateway):
        """Test SubAgent Factory adapter routes through gateway."""
        adapter = SubAgentFactoryAdapter(unified_gateway)
        task = TaskData(
            title="Create subagent",
            description="M-MDP subagent factory call",
            agent_id="factory",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"agent_id": "subagent_1"})

        result = await adapter.execute(task, executor)

        assert result.success is True
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_adapter_execution(self, unified_gateway):
        """Test WebSocket LangGraph adapter routes through gateway."""
        adapter = WebSocketLangGraphAdapter(unified_gateway)
        task = TaskData(
            title="Stream response",
            description="Real-time streaming execution",
            agent_id="stream",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"chunks": ["data1", "data2"]})

        result = await adapter.execute(task, executor)

        assert result.success is True
        executor.assert_called_once()


class TestAdapterGovernanceEnforcement:
    """Test that adapters enforce governance through gateway."""

    @pytest.mark.asyncio
    async def test_governance_enforced_in_all_adapters(self, unified_gateway, mock_ethics_gate):
        """Test governance pipeline is executed for all adapters."""
        # Create blocked evaluation to trigger governance failure
        blocked_eval = EthicsEvaluation(
            level=EthicsLevel.BLOCKED,
            score=10.0,
            concerns=["Security violation"],
            recommendations=["Reject"],
            category_scores={},
            timestamp=datetime.now(timezone.utc),
        )
        mock_ethics_gate.evaluate = AsyncMock(return_value=blocked_eval)

        adapters = [
            EnhancedBaseAgentAdapter(unified_gateway),
            OrchestratorAdapter(unified_gateway),
            CVAStateMachineAdapter(unified_gateway),
            DramatiqWorkflowAdapter(unified_gateway),
            SubAgentFactoryAdapter(unified_gateway),
            WebSocketLangGraphAdapter(unified_gateway),
        ]

        task = TaskData(
            title="Test",
            description="Test",
            agent_id="test",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"result": "should-not-execute"})

        for adapter in adapters:
            result = await adapter.execute(task, executor)
            # All adapters should reject due to ethics gate blocking
            assert result.success is False
            assert "blocked" in result.error_message.lower()


class TestAdapterCircuitBreaker:
    """Test circuit breaker behavior across adapters."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_tracks_across_adapters(self, unified_gateway):
        """Test circuit breaker tracks failures across different adapters."""
        task = TaskData(
            title="Test",
            description="Test",
            agent_id="agent_123",
            tenant_id=1,
        )

        # Use different adapters but same agent_id
        adapter1 = EnhancedBaseAgentAdapter(unified_gateway)
        adapter2 = OrchestratorAdapter(unified_gateway)

        # Simulate first adapter execution
        executor1 = AsyncMock(return_value={"status": "success"})
        result1 = await adapter1.execute(task, executor1)
        assert result1.success is True

        # Check circuit breaker state
        status = unified_gateway.get_breaker_status("agent_123")
        assert status["failure_count"] == 0

        # Second adapter execution with same agent
        executor2 = AsyncMock(return_value={"status": "success"})
        result2 = await adapter2.execute(task, executor2)
        assert result2.success is True

        # Circuit breaker should track both
        status = unified_gateway.get_breaker_status("agent_123")
        assert status["failure_count"] == 0


class TestMultiPathIntegration:
    """Test integration across multiple execution paths."""

    @pytest.mark.asyncio
    async def test_parallel_execution_through_adapters(self, unified_gateway):
        """Test parallel task execution through different adapters."""
        tasks = [
            TaskData(
                id="task_1",
                title="Task 1",
                description="Test",
                agent_id="agent_1",
                tenant_id=1,
            ),
            TaskData(
                id="task_2",
                title="Task 2",
                description="Test",
                agent_id="agent_2",
                tenant_id=1,
            ),
            TaskData(
                id="task_3",
                title="Task 3",
                description="Test",
                agent_id="agent_3",
                tenant_id=1,
            ),
        ]

        adapters = [
            EnhancedBaseAgentAdapter(unified_gateway),
            OrchestratorAdapter(unified_gateway),
            CVAStateMachineAdapter(unified_gateway),
        ]

        async def execute_task(adapter, task):
            executor = AsyncMock(return_value={"result": "success"})
            return await adapter.execute(task, executor)

        # Run parallel executions
        results = await asyncio.gather(*[execute_task(adapters[i], tasks[i]) for i in range(3)])

        assert len(results) == 3
        assert all(r.success for r in results)
        assert len(unified_gateway.get_all_breaker_statuses()) == 3  # 3 unique agents
