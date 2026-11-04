"""
Unit tests for UnifiedAgentGateway (Phase A implementation).
Tests mandatory governance pipeline, circuit breaker, and deadline propagation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.agent_registry import AgentRegistry
from src.core.agents.unified_gateway import (
    ExecutionDeadline,
    UnifiedAgentGateway,
    UnifiedAgentGatewayConfig,
)
from src.core.ethics.ethics_gate import EthicsEvaluation, EthicsGate, EthicsLevel
from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightGate, OversightResult
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType, TaskPriority, TaskStatus


@pytest.fixture
def task_data():
    """Create test task data."""
    return TaskData(
        id="test_task_1",
        title="Test Task",
        description="Test task description",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.PENDING,
        agent_id="test_agent_1",
        tenant_id=1,
    )


@pytest.fixture
def mock_registry():
    """Create mock agent registry."""
    registry = AsyncMock(spec=AgentRegistry)
    registry.get_agent_by_id = AsyncMock(
        return_value={"agent_id": "test_agent_1", "agent_type": AgentType.SPECIALIST}
    )
    return registry


@pytest.fixture
def mock_ethics_gate():
    """Create mock ethics gate."""
    from src.core.ethics.ethics_gate import EthicsEvaluation, EthicsLevel

    gate = AsyncMock(spec=EthicsGate)

    # Create a mock evaluation
    evaluation = EthicsEvaluation(
        level=EthicsLevel.SAFE,
        score=100.0,
        concerns=[],
        recommendations=["Proceed"],
        category_scores={"privacy": 100.0, "safety": 100.0},
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
def gateway(mock_registry, mock_ethics_gate, mock_oversight_gate):
    """Create gateway with mocked dependencies."""
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


class TestUnifiedGatewayInitialization:
    """Test gateway initialization."""

    def test_gateway_creation(self, gateway):
        """Test gateway is created with proper configuration."""
        assert gateway is not None
        assert gateway.config.default_timeout_seconds == 10.0
        assert gateway.config.enable_ethics_gate is True
        assert gateway.config.enable_circuit_breaker is True

    def test_gateway_with_default_gates(self, mock_registry, caplog):
        """Test gateway uses DI for oversight_gate -- ADR-034 Gov-DI pattern.

        oversight_gate is None by default (DI-only); ethics_gate retains its default.
        A WARNING is emitted when enable_oversight_gate=True but no gate is injected.
        """
        import logging

        with caplog.at_level(logging.WARNING, logger="src.core.agents.unified_gateway"):
            gateway = UnifiedAgentGateway(registry=mock_registry)

        assert isinstance(gateway.ethics_gate, EthicsGate)
        assert gateway.oversight_gate is None, (
            "ADR-034: oversight_gate must be injected -- not auto-constructed"
        )
        assert any(
            "oversight_gate=None" in record.message and "SKIPPED" in record.message
            for record in caplog.records
        ), "Gateway must warn when oversight_gate is None and enable_oversight_gate=True"


class TestGovernancePipeline:
    """Test mandatory governance pipeline."""

    @pytest.mark.asyncio
    async def test_ethics_gate_called(self, gateway, task_data, mock_ethics_gate):
        """Test ethics gate is called in pipeline."""
        executor = AsyncMock(return_value={"status": "success"})

        await gateway.execute(task_data, executor)

        mock_ethics_gate.evaluate.assert_called_once()
        args = mock_ethics_gate.evaluate.call_args
        assert task_data.description in str(args)

    @pytest.mark.asyncio
    async def test_oversight_gate_called(self, gateway, task_data, mock_oversight_gate):
        """Test oversight gate is called in pipeline."""
        executor = AsyncMock(return_value={"status": "success"})

        await gateway.execute(task_data, executor)

        mock_oversight_gate.check.assert_called_once()
        args = mock_oversight_gate.check.call_args
        assert args[1]["tenant_id"] == task_data.tenant_id

    @pytest.mark.asyncio
    async def test_governance_pipeline_rejection(self, gateway, task_data, mock_ethics_gate):
        """Test execution rejected by ethics gate."""
        # Create blocked evaluation
        blocked_eval = EthicsEvaluation(
            level=EthicsLevel.BLOCKED,
            score=10.0,
            concerns=["Unethical query"],
            recommendations=["Reject"],
            category_scores={},
            timestamp=datetime.now(timezone.utc),
        )
        mock_ethics_gate.evaluate = AsyncMock(return_value=blocked_eval)
        executor = AsyncMock()

        result = await gateway.execute(task_data, executor)

        assert result.success is False
        assert "blocked" in result.error_message.lower()
        executor.assert_not_called()

    @pytest.mark.asyncio
    async def test_governance_pipeline_approval(
        self, gateway, task_data, mock_ethics_gate, mock_oversight_gate
    ):
        """Test execution approved by all gates."""
        executor = AsyncMock(return_value={"status": "success"})

        result = await gateway.execute(task_data, executor)

        assert result.success is True
        executor.assert_called_once()
        mock_ethics_gate.evaluate.assert_called_once()
        mock_oversight_gate.check.assert_called_once()

    @pytest.mark.asyncio
    async def test_gates_can_be_disabled(self, mock_registry):
        """Test gates can be disabled via config."""
        gateway = UnifiedAgentGateway(
            registry=mock_registry,
            config=UnifiedAgentGatewayConfig(
                enable_ethics_gate=False,
                enable_oversight_gate=False,
            ),
        )
        task_data = TaskData(
            title="Test",
            description="Test",
            agent_id="test_agent",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"status": "success"})

        result = await gateway.execute(task_data, executor)

        assert result.success is True
        executor.assert_called_once()


class TestDeadlinePropagation:
    """Test deadline and timeout propagation."""

    @pytest.mark.asyncio
    async def test_default_deadline_created(self, gateway, task_data):
        """Test default deadline is created if not provided."""
        executor = AsyncMock(return_value={"status": "success"})

        await gateway.execute(task_data, executor)

        # Verify executor was called (deadline was handled)
        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_deadline_on_task_data(self, gateway, task_data):
        """Test deadline from task data is used."""
        future_deadline = datetime.now(timezone.utc) + timedelta(seconds=30)
        task_data.execution_deadline = future_deadline

        executor = AsyncMock(return_value={"status": "success"})
        await gateway.execute(task_data, executor)

        executor.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self, mock_registry, mock_ethics_gate, mock_oversight_gate):
        """Test timeout is enforced on executor."""
        gateway = UnifiedAgentGateway(
            registry=mock_registry,
            ethics_gate=mock_ethics_gate,
            oversight_gate=mock_oversight_gate,
            config=UnifiedAgentGatewayConfig(default_timeout_seconds=0.1),
        )
        task_data = TaskData(
            title="Test",
            description="Test",
            agent_id="test_agent",
            tenant_id=1,
        )

        async def slow_executor(task):
            await asyncio.sleep(1.0)  # Intentionally slow
            return {"status": "success"}

        result = await gateway.execute(task_data, slow_executor)

        assert result.success is False
        assert "timed out" in result.error_message.lower()


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_created_per_agent(self, gateway, task_data):
        """Test circuit breaker is created per agent."""
        executor = AsyncMock(return_value={"status": "success"})

        await gateway.execute(task_data, executor)

        assert "test_agent_1" in gateway._circuit_breakers

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_success(self, gateway, task_data):
        """Test circuit breaker records successful execution."""
        executor = AsyncMock(return_value={"status": "success"})

        result = await gateway.execute(task_data, executor)

        assert result.success is True
        breaker = gateway._circuit_breakers["test_agent_1"]
        assert breaker.get_state()["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_timeout(
        self, mock_registry, mock_ethics_gate, mock_oversight_gate
    ):
        """Test circuit breaker records timeout as failure."""
        gateway = UnifiedAgentGateway(
            registry=mock_registry,
            ethics_gate=mock_ethics_gate,
            oversight_gate=mock_oversight_gate,
            config=UnifiedAgentGatewayConfig(default_timeout_seconds=0.05),
        )
        task_data = TaskData(
            title="Test",
            description="Test",
            agent_id="test_agent",
            tenant_id=1,
        )

        async def slow_executor(task):
            await asyncio.sleep(1.0)
            return {"status": "success"}

        await gateway.execute(task_data, slow_executor)

        breaker = gateway._circuit_breakers["test_agent"]
        assert breaker.get_state()["failure_count"] > 0

    @pytest.mark.asyncio
    async def test_circuit_breaker_can_be_disabled(
        self, mock_registry, mock_ethics_gate, mock_oversight_gate
    ):
        """Test circuit breaker can be disabled."""
        gateway = UnifiedAgentGateway(
            registry=mock_registry,
            ethics_gate=mock_ethics_gate,
            oversight_gate=mock_oversight_gate,
            config=UnifiedAgentGatewayConfig(enable_circuit_breaker=False),
        )
        task_data = TaskData(
            title="Test",
            description="Test",
            agent_id="test_agent",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"status": "success"})

        result = await gateway.execute(task_data, executor)

        assert result.success is True
        # Execution succeeds - circuit breaker is disabled so checks are skipped
        executor.assert_called_once()


class TestExecutionResult:
    """Test execution result formatting."""

    @pytest.mark.asyncio
    async def test_successful_result_structure(self, gateway, task_data):
        """Test successful execution result structure."""
        executor = AsyncMock(return_value={"output": "success"})

        result = await gateway.execute(task_data, executor)

        assert isinstance(result, ExecutionResult)
        assert result.task_id == task_data.id
        assert result.success is True
        assert result.result_data == {"output": "success"}
        assert result.execution_time >= 0.0
        assert result.error_message is None

    @pytest.mark.asyncio
    async def test_failed_result_structure(self, gateway, task_data, mock_ethics_gate):
        """Test failed execution result structure."""
        # Create blocked ethics evaluation
        blocked_eval = EthicsEvaluation(
            level=EthicsLevel.BLOCKED,
            score=10.0,
            concerns=["Test failure"],
            recommendations=["Reject"],
            category_scores={},
            timestamp=datetime.now(timezone.utc),
        )
        mock_ethics_gate.evaluate = AsyncMock(return_value=blocked_eval)
        executor = AsyncMock()

        result = await gateway.execute(task_data, executor)

        assert isinstance(result, ExecutionResult)
        assert result.task_id == task_data.id
        assert result.success is False
        assert result.result_data is None
        assert result.execution_time >= 0.0
        assert "blocked" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_execution_time_tracked(self, gateway, task_data):
        """Test execution time is properly tracked."""

        async def slow_executor(task):
            await asyncio.sleep(0.1)
            return {"status": "success"}

        result = await gateway.execute(task_data, slow_executor)

        assert result.success is True
        assert result.execution_time >= 0.1


class TestBreakerStatusQueries:
    """Test circuit breaker status queries."""

    @pytest.mark.asyncio
    async def test_get_breaker_status(self, gateway, task_data):
        """Test getting breaker status for specific agent."""
        executor = AsyncMock(return_value={"status": "success"})
        await gateway.execute(task_data, executor)

        status = gateway.get_breaker_status("test_agent_1")

        assert status is not None
        assert "state" in status
        assert "failure_count" in status

    @pytest.mark.asyncio
    async def test_get_all_breaker_statuses(self, gateway):
        """Test getting all breaker statuses."""
        task1 = TaskData(
            title="Task 1",
            description="Test",
            agent_id="agent_1",
            tenant_id=1,
        )
        task2 = TaskData(
            title="Task 2",
            description="Test",
            agent_id="agent_2",
            tenant_id=1,
        )
        executor = AsyncMock(return_value={"status": "success"})

        await gateway.execute(task1, executor)
        await gateway.execute(task2, executor)

        statuses = gateway.get_all_breaker_statuses()

        assert len(statuses) == 2
        assert "agent_1" in statuses
        assert "agent_2" in statuses
