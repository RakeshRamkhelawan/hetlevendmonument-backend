"""
Unit tests for EnhancedBaseAgent (base_agent.py).

Covers: initialization, tenant isolation, validate_task, emit_event,
process_task, shutdown, get_performance_metrics, concurrent task limits.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.shared.interfaces import (
    AgentCapability,
    AgentStatus,
    ExecutionResult,
    SystemEvent,
    TaskData,
)
from src.core.types import AgentType


# Concrete subclass for testing (since EnhancedBaseAgent is abstract)
class _TestAgent:
    """Lazily imported to avoid circular import issues at module level."""

    _cls = None

    @classmethod
    def get_class(cls):
        if cls._cls is None:
            from src.core.agents.base_agent import EnhancedBaseAgent

            class ConcreteTestAgent(EnhancedBaseAgent):
                async def _execute_task(self, task: TaskData) -> ExecutionResult:
                    return ExecutionResult(
                        task_id=task.id,
                        success=True,
                        result_data={"output": "done"},
                    )

            cls._cls = ConcreteTestAgent
        return cls._cls


@pytest.fixture
def make_agent():
    """Factory fixture for creating test agents with mocked dependencies."""

    def _make(tenant_id=1, agent_id="test-agent", agent_type=AgentType.SPECIALIST, **kwargs):
        AgentClass = _TestAgent.get_class()
        with (
            patch("src.core.agents.base_agent.get_settings") as mock_settings,
            patch("src.core.agents.base_agent.get_feature_flag", return_value=False),
            patch("src.core.ai.router.AIRouter"),
            patch("src.core.ai.explainability.ReasoningTrace"),
        ):
            mock_settings.return_value = MagicMock(max_concurrent_tasks=5)
            agent = AgentClass(
                agent_id=agent_id,
                agent_type=agent_type,
                tenant_id=tenant_id,
                **kwargs,
            )
        return agent

    return _make


@pytest.fixture
def agent(make_agent):
    return make_agent()


def _make_task(task_id="task_1", metadata=None):
    return TaskData(
        id=task_id,
        title="Test Task",
        description="A test task",
        metadata=metadata or {"type": "text"},
    )


class TestInitialization:
    """Tests for agent initialization and tenant validation."""

    def test_creates_with_valid_tenant_id(self, make_agent):
        agent = make_agent(tenant_id=42)
        assert agent.tenant_id == 42

    def test_rejects_missing_tenant_id(self, make_agent):
        with pytest.raises(ValueError, match="invalid tenant_id"):
            make_agent(tenant_id=None)

    def test_rejects_zero_tenant_id(self, make_agent):
        with pytest.raises(ValueError, match="invalid tenant_id"):
            make_agent(tenant_id=0)

    def test_rejects_negative_tenant_id(self, make_agent):
        with pytest.raises(ValueError, match="invalid tenant_id"):
            make_agent(tenant_id=-1)

    def test_sets_agent_id_and_type(self, make_agent):
        agent = make_agent(agent_id="my-agent", agent_type=AgentType.ANALYZER)
        assert agent.agent_id == "my-agent"
        assert agent.agent_type == AgentType.ANALYZER

    def test_initial_metrics_are_zero(self, agent):
        assert agent._tasks_processed == 0
        assert agent._total_execution_time == 0.0
        assert agent._errors_count == 0
        assert agent._last_error is None

    def test_custom_event_emitter(self, make_agent):
        custom_emitter = AsyncMock()
        agent = make_agent(event_emitter=custom_emitter)
        assert agent.event_emitter is custom_emitter


class TestValidateTask:
    """Tests for validate_task()."""

    @pytest.mark.asyncio
    async def test_accepts_text_type(self, agent):
        task = _make_task(metadata={"type": "text"})
        assert await agent.validate_task(task) is True

    @pytest.mark.asyncio
    async def test_accepts_general_type(self, agent):
        task = _make_task(metadata={"type": "general"})
        assert await agent.validate_task(task) is True

    @pytest.mark.asyncio
    async def test_rejects_unknown_type(self, agent):
        task = _make_task(metadata={"type": "quantum_compute"})
        assert await agent.validate_task(task) is False

    @pytest.mark.asyncio
    async def test_accepts_when_no_type_defaults_general(self, agent):
        task = _make_task(metadata={})
        assert await agent.validate_task(task) is True


class TestEmitEvent:
    """Tests for emit_event()."""

    @pytest.mark.asyncio
    async def test_calls_event_emitter(self, make_agent):
        emitter = AsyncMock()
        agent = make_agent(event_emitter=emitter)

        await agent.emit_event("test_event", {"key": "value"})

        emitter.assert_awaited_once()
        event = emitter.call_args[0][0]
        assert isinstance(event, SystemEvent)
        assert event.event_type == "test_event"

    @pytest.mark.asyncio
    async def test_swallows_emitter_exception(self, make_agent):
        emitter = AsyncMock(side_effect=RuntimeError("boom"))
        agent = make_agent(event_emitter=emitter)

        # Should not raise
        await agent.emit_event("test_event", {})

    @pytest.mark.asyncio
    async def test_noop_when_no_emitter(self, make_agent):
        agent = make_agent(event_emitter=None)
        # Default emitter is set to _default_event_emitter, not None
        # Just verify it doesn't raise
        await agent.emit_event("test_event", {})


class TestProcessTask:
    """Tests for process_task()."""

    @pytest.mark.asyncio
    async def test_successful_task_returns_success(self, agent):
        task = _make_task()

        with (
            patch.object(agent, "emit_event", new_callable=AsyncMock),
            patch("src.core.ai.explainability.ReasoningTrace") as MockTrace,
            patch("src.core.ai.explainability.ReasoningStepType"),
        ):
            mock_trace = MagicMock()
            mock_trace.finalize.return_value = {}
            MockTrace.return_value = mock_trace

            result = await agent.process_task(task)

        assert result.success is True
        assert result.task_id == task.id

    @pytest.mark.asyncio
    async def test_updates_metrics_on_success(self, agent):
        task = _make_task()

        with (
            patch.object(agent, "emit_event", new_callable=AsyncMock),
            patch("src.core.ai.explainability.ReasoningTrace") as MockTrace,
            patch("src.core.ai.explainability.ReasoningStepType"),
        ):
            mock_trace = MagicMock()
            mock_trace.finalize.return_value = {}
            MockTrace.return_value = mock_trace

            await agent.process_task(task)

        assert agent._tasks_processed == 1
        assert agent._total_execution_time > 0

    @pytest.mark.asyncio
    async def test_rejects_invalid_task(self, agent):
        task = _make_task(metadata={"type": "quantum_compute"})

        with (
            patch.object(agent, "emit_event", new_callable=AsyncMock),
            patch("src.core.ai.explainability.ReasoningTrace") as MockTrace,
            patch("src.core.ai.explainability.ReasoningStepType"),
        ):
            mock_trace = MagicMock()
            MockTrace.return_value = mock_trace

            result = await agent.process_task(task)

        assert result.success is False
        assert "validation failed" in result.error_message

    @pytest.mark.asyncio
    async def test_rejects_when_at_capacity(self, make_agent):
        agent = make_agent()
        # Fill up task slots
        for i in range(5):
            agent._current_tasks[f"task_{i}"] = MagicMock()

        task = _make_task(task_id="task_overflow")

        with (
            patch.object(agent, "emit_event", new_callable=AsyncMock),
            patch("src.core.ai.explainability.ReasoningTrace") as MockTrace,
            patch("src.core.ai.explainability.ReasoningStepType"),
        ):
            mock_trace = MagicMock()
            MockTrace.return_value = mock_trace

            result = await agent.process_task(task)

        assert result.success is False
        assert "at capacity" in result.error_message

    @pytest.mark.asyncio
    async def test_cleans_up_task_on_completion(self, agent):
        task = _make_task()

        with (
            patch.object(agent, "emit_event", new_callable=AsyncMock),
            patch("src.core.ai.explainability.ReasoningTrace") as MockTrace,
            patch("src.core.ai.explainability.ReasoningStepType"),
        ):
            mock_trace = MagicMock()
            mock_trace.finalize.return_value = {}
            MockTrace.return_value = mock_trace

            await agent.process_task(task)

        assert task.id not in agent._current_tasks


class TestShutdown:
    """Tests for shutdown()."""

    @pytest.mark.asyncio
    async def test_shutdown_with_no_tasks(self, agent):
        with patch.object(agent, "emit_event", new_callable=AsyncMock) as mock_emit:
            await agent.shutdown()
            # Should emit agent_shutdown event
            mock_emit.assert_awaited()
            event_types = [call.args[0] for call in mock_emit.call_args_list]
            assert "agent_shutdown" in event_types

    @pytest.mark.asyncio
    async def test_shutdown_logs_pending_tasks(self, agent):
        agent._current_tasks["stuck_task"] = MagicMock()

        with (
            patch.object(agent, "emit_event", new_callable=AsyncMock),
            # Patch time.time so the max_wait condition (30 s) is immediately
            # exceeded without ever sleeping.  Patching asyncio.sleep instead
            # breaks the event-loop's ability to process wait_for timeouts,
            # causing the test to hang for 30 real seconds.
            patch("src.core.agents.base_agent.time") as mock_time,
        ):
            # wait_start = 0; second call returns 100 s elapsed → loop exits
            mock_time.time.side_effect = [0.0, 100.0]
            await agent.shutdown()

        # Stuck task is still present: the warning branch was taken
        assert "stuck_task" in agent._current_tasks


class TestGetPerformanceMetrics:
    """Tests for get_performance_metrics()."""

    def test_returns_all_keys(self, agent):
        metrics = agent.get_performance_metrics()
        expected_keys = {
            "agent_id",
            "agent_type",
            "tasks_processed",
            "total_execution_time",
            "average_execution_time",
            "errors_count",
            "error_rate",
            "current_load",
            "max_concurrent_tasks",
            "current_tasks_count",
            "capabilities_count",
            "is_active",
            "initialization_time",
        }
        assert expected_keys.issubset(set(metrics.keys()))

    def test_zero_division_safe(self, agent):
        metrics = agent.get_performance_metrics()
        assert metrics["average_execution_time"] == 0.0
        assert metrics["error_rate"] == 0.0

    def test_reflects_state_after_processing(self, agent):
        agent._tasks_processed = 10
        agent._total_execution_time = 25.0
        agent._errors_count = 2

        metrics = agent.get_performance_metrics()
        assert metrics["tasks_processed"] == 10
        assert metrics["average_execution_time"] == 2.5
        assert metrics["error_rate"] == 0.2
