"""
Comprehensive tests for src/core/agents/base_agent.py
Coverage target: 100% of base agent functionality
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.agents.base_agent import (
    EnhancedBaseAgent,
    _setup_event_emitter,
    _setup_llm_client,
    _setup_memory_store,
    create_agent_with_dependencies,
)
from src.core.shared.interfaces import (
    AgentCapability,
    AgentType,
    ExecutionResult,
    SystemEvent,
    TaskData,
)


TEST_TENANT_ID = 1


# Concrete implementation for testing
class ConcreteTestAgent(EnhancedBaseAgent):
    """Concrete agent implementation for testing"""

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Simple test implementation"""
        return ExecutionResult(
            task_id=task.id, success=True, result_data={"message": "Task completed"}
        )


class TestEnhancedBaseAgentInitialization:
    """Test EnhancedBaseAgent initialization"""

    def test_initialization_basic(self):
        """Test basic agent initialization"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-1",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        assert agent.agent_id == "test-agent-1"
        assert agent.agent_type == AgentType.SPECIALIST
        assert agent._tasks_processed == 0
        assert agent._errors_count == 0

    def test_initialization_rejects_missing_tenant_id(self):
        """Test initialization rejects missing tenant context"""
        with pytest.raises(ValueError, match="invalid tenant_id"):
            ConcreteTestAgent(
                agent_id="test-agent-missing-tenant",
                agent_type=AgentType.SPECIALIST,
                tenant_id=None,
            )

    def test_initialization_with_llm_client(self):
        """Test initialization with LLM client"""
        mock_llm = Mock()
        agent = ConcreteTestAgent(
            agent_id="test-agent-2",
            agent_type=AgentType.CVA,
            tenant_id=TEST_TENANT_ID,
            llm_client=mock_llm,
        )

        assert agent.llm_client == mock_llm

    def test_initialization_with_memory_store(self):
        """Test initialization with memory store"""
        mock_memory = Mock()
        agent = ConcreteTestAgent(
            agent_id="test-agent-3",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
            memory_store=mock_memory,
        )

        assert agent.memory_store == mock_memory

    def test_initialization_with_event_emitter(self):
        """Test initialization with custom event emitter"""
        mock_emitter = AsyncMock()
        agent = ConcreteTestAgent(
            agent_id="test-agent-4",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
            event_emitter=mock_emitter,
        )

        assert agent.event_emitter == mock_emitter

    def test_initialization_default_event_emitter(self):
        """Test initialization creates default event emitter"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-5",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        assert agent.event_emitter is not None

    @patch("src.core.agents.base_agent.get_settings")
    def test_initialization_loads_settings(self, mock_settings):
        """Test initialization loads settings"""
        mock_config = Mock()
        mock_config.max_concurrent_tasks = 5
        mock_settings.return_value = mock_config

        agent = ConcreteTestAgent(
            agent_id="test-agent-6",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        assert agent._max_concurrent_tasks == 5


class TestAgentInitialize:
    """Test agent initialize method"""

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful agent initialization"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-7",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        result = await agent.initialize()

        assert result is True
        assert agent._initialization_time is not None

    @pytest.mark.asyncio
    async def test_initialize_sets_initialization_time(self):
        """Test initialize sets initialization time"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-8",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        before = datetime.now(timezone.utc)
        await agent.initialize()
        after = datetime.now(timezone.utc)

        assert before <= agent._initialization_time <= after

    @pytest.mark.asyncio
    async def test_initialize_capabilities(self):
        """Test initialize sets up capabilities"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-9",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        await agent.initialize()

        capabilities = await agent.get_capabilities()
        assert len(capabilities) > 0

    @pytest.mark.asyncio
    async def test_initialize_emits_event(self):
        """Test initialize emits agent_initialized event"""
        mock_emitter = AsyncMock()
        agent = ConcreteTestAgent(
            agent_id="test-agent-10",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
            event_emitter=mock_emitter,
        )

        await agent.initialize()

        mock_emitter.assert_called()


class TestProcessTask:
    """Test process_task method"""

    @pytest.mark.asyncio
    async def test_process_task_success(self):
        """Test successful task processing"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-11",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        task = TaskData(
            id="task-1",
            title="Test Task",
            description="Test task description",
            metadata={"type": "text"},
        )

        result = await agent.process_task(task)

        assert result.success is True
        assert result.task_id == "task-1"

    @pytest.mark.asyncio
    async def test_process_task_increments_counter(self):
        """Test task processing increments task counter"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-12",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        task = TaskData(
            id="task-2",
            title="Test Task",
            description="Test task description",
            metadata={"type": "text"},
        )

        initial_count = agent._tasks_processed
        await agent.process_task(task)

        assert agent._tasks_processed == initial_count + 1

    @pytest.mark.asyncio
    async def test_process_task_tracks_execution_time(self):
        """Test task processing tracks execution time"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-13",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        task = TaskData(
            id="task-3",
            title="Test Task",
            description="Test task description",
            metadata={"type": "text"},
        )

        result = await agent.process_task(task)

        assert result.execution_time is not None
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_process_task_validation_failure(self):
        """Test task processing with validation failure"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-14",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        # Task with unsupported type
        task = TaskData(
            id="task-4",
            title="Test Task",
            description="Test task description",
            metadata={"type": "unsupported_type"},
        )

        # Patch validate_task to return False
        with patch.object(agent, "validate_task", return_value=False):
            result = await agent.process_task(task)

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_process_task_capacity_limit(self):
        """Test task processing respects capacity limit"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-15",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        agent._max_concurrent_tasks = 1
        await agent.initialize()

        # Create task that blocks
        async def slow_execute(task):
            await asyncio.sleep(0.5)
            return ExecutionResult(task_id=task.id, success=True)

        with patch.object(agent, "_execute_task", side_effect=slow_execute):
            task1 = TaskData(
                id="task-5",
                title="Task 1",
                description="Task 1 description",
                metadata={"type": "text"},
            )
            task2 = TaskData(
                id="task-6",
                title="Task 2",
                description="Task 2 description",
                metadata={"type": "text"},
            )

            # Start first task
            task1_future = asyncio.create_task(agent.process_task(task1))
            await asyncio.sleep(0.1)  # Let it start

            # Try second task (should be rejected)
            result2 = await agent.process_task(task2)

            assert result2.success is False
            assert "capacity" in result2.error_message.lower()

            # Clean up
            await task1_future

    @pytest.mark.asyncio
    async def test_process_task_handles_exception(self):
        """Test task processing handles exceptions"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-16",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        # Patch _execute_task to raise exception
        with patch.object(agent, "_execute_task", side_effect=Exception("Test error")):
            task = TaskData(
                id="task-7",
                title="Test",
                description="Test description",
                metadata={"type": "text"},
            )
            result = await agent.process_task(task)

        assert result.success is False
        assert "Test error" in result.error_message
        assert agent._errors_count == 1

    @pytest.mark.asyncio
    async def test_process_task_creates_reasoning_trace(self):
        """Test task processing creates reasoning trace"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-17",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        task = TaskData(
            id="task-8",
            title="Test",
            description="Test description",
            metadata={"type": "text"},
        )
        await agent.process_task(task)

        assert agent.reasoning_trace is not None


class TestValidateTask:
    """Test validate_task method"""

    @pytest.mark.asyncio
    async def test_validate_task_text_type(self):
        """Test task validation for text type"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-18",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        task = TaskData(
            id="task-9",
            title="Test",
            description="Test description",
            metadata={"type": "text"},
        )
        result = await agent.validate_task(task)

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_task_general_type(self):
        """Test task validation for general type"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-19",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        task = TaskData(
            id="task-10",
            title="Test",
            description="Test description",
            metadata={"type": "general"},
        )
        result = await agent.validate_task(task)

        assert result is True


class TestGetStatus:
    """Test get_status method"""

    @pytest.mark.asyncio
    async def test_get_status_includes_metrics(self):
        """Test get_status includes metrics"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-20",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        status = await agent.get_status()

        assert status.metrics is not None
        assert "tasks_processed" in status.metrics
        assert "errors_count" in status.metrics

    @pytest.mark.asyncio
    async def test_get_status_calculates_average_execution_time(self):
        """Test get_status calculates average execution time"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-21",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        # Process a task
        task = TaskData(
            id="task-11",
            title="Test",
            description="Test description",
            metadata={"type": "text"},
        )
        await agent.process_task(task)

        status = await agent.get_status()

        assert status.metrics["average_execution_time"] > 0

    @pytest.mark.asyncio
    async def test_get_status_includes_uptime(self):
        """Test get_status includes uptime"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-22",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        await asyncio.sleep(0.1)

        status = await agent.get_status()

        assert status.metrics["uptime_seconds"] > 0


class TestEventEmission:
    """Test event emission"""

    @pytest.mark.asyncio
    async def test_emit_event_calls_emitter(self):
        """Test emit_event calls event emitter"""
        mock_emitter = AsyncMock()
        agent = ConcreteTestAgent(
            agent_id="test-agent-23",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
            event_emitter=mock_emitter,
        )

        await agent.emit_event("test_event", {"key": "value"})

        mock_emitter.assert_called_once()
        call_args = mock_emitter.call_args[0][0]
        assert isinstance(call_args, SystemEvent)
        assert call_args.event_type == "test_event"

    @pytest.mark.asyncio
    async def test_emit_event_handles_emitter_error(self):
        """Test emit_event handles emitter errors"""
        mock_emitter = AsyncMock(side_effect=Exception("Emitter error"))
        agent = ConcreteTestAgent(
            agent_id="test-agent-24",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
            event_emitter=mock_emitter,
        )

        # Should not raise
        await agent.emit_event("test_event", {"key": "value"})


class TestShutdown:
    """Test shutdown method"""

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_tasks(self):
        """Test shutdown waits for current tasks"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-25",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        await agent.shutdown()

        assert len(agent._current_tasks) == 0

    @pytest.mark.asyncio
    async def test_shutdown_emits_event(self):
        """Test shutdown emits shutdown event"""
        mock_emitter = AsyncMock()
        agent = ConcreteTestAgent(
            agent_id="test-agent-26",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
            event_emitter=mock_emitter,
        )
        await agent.initialize()

        await agent.shutdown()

        # Check for shutdown event
        calls = [call[0][0] for call in mock_emitter.call_args_list]
        shutdown_events = [e for e in calls if e.event_type == "agent_shutdown"]
        assert len(shutdown_events) > 0


class TestGetPerformanceMetrics:
    """Test get_performance_metrics method"""

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self):
        """Test get_performance_metrics returns complete data"""
        agent = ConcreteTestAgent(
            agent_id="test-agent-27",
            agent_type=AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )
        await agent.initialize()

        metrics = agent.get_performance_metrics()

        assert metrics["agent_id"] == "test-agent-27"
        assert "tasks_processed" in metrics
        assert "error_rate" in metrics
        assert "current_load" in metrics


class TestFactoryFunction:
    """Test create_agent_with_dependencies factory"""

    @pytest.mark.asyncio
    @patch("src.core.agents.base_agent.get_feature_flag")
    async def test_create_agent_with_dependencies(self, mock_feature_flag):
        """Test factory creates agent with dependencies"""
        mock_feature_flag.return_value = False

        agent = await create_agent_with_dependencies(
            ConcreteTestAgent,
            "factory-agent-1",
            AgentType.SPECIALIST,
            tenant_id=TEST_TENANT_ID,
        )

        assert agent.agent_id == "factory-agent-1"
        assert agent.agent_type == AgentType.SPECIALIST

    @pytest.mark.asyncio
    @patch("src.core.agents.base_agent.get_feature_flag")
    async def test_create_agent_with_dependencies_rejects_missing_tenant(self, mock_feature_flag):
        """Test factory rejects missing tenant context"""
        mock_feature_flag.return_value = False

        with pytest.raises(ValueError, match="invalid tenant_id"):
            await create_agent_with_dependencies(
                ConcreteTestAgent,
                "factory-agent-missing-tenant",
                AgentType.SPECIALIST,
                tenant_id=None,
            )


class TestUtilityFunctions:
    """Test utility setup functions"""

    @pytest.mark.asyncio
    async def test_setup_llm_client(self):
        """_setup_llm_client geeft het taalmodel van de TENANT van de agent (brief 2026-10-20)."""
        result = await _setup_llm_client(TEST_TENANT_ID)
        assert type(result).__name__ == "TenantTaalmodel"

    @pytest.mark.asyncio
    async def test_setup_memory_store(self):
        """Test _setup_memory_store returns dict when container is available"""
        result = await _setup_memory_store(tenant_id=TEST_TENANT_ID)
        # When the container is available, returns a dict with session_factory and tenant_id
        if result is not None:
            assert isinstance(result, dict)
            assert "session_factory" in result
            assert "tenant_id" in result
        # If container is unavailable (e.g. CI without DB), returns None - also valid

    @pytest.mark.asyncio
    async def test_setup_event_emitter(self):
        """Test _setup_event_emitter"""
        emitter = await _setup_event_emitter()
        assert emitter is not None

        # Test it can be called
        event = SystemEvent(event_type="test", source="test", data={})
        await emitter(event)
