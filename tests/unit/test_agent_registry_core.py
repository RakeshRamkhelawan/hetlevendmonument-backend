"""
Unit tests for core/agents/agent_registry.py - Multi-Agent Registry System
Coverage target: 0% -> 80%+
Created: November 28, 2025

Tests agent registration, discovery, task routing, and health monitoring.
This is a CRITICAL module for the multi-agent coordination system.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import List, Set
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.agents.agent_registry import AgentRegistry
from src.core.shared.interfaces import Agent, AgentCapability, AgentType, ExecutionResult, TaskData


@pytest.fixture(autouse=True)
def set_test_mode():
    """Set testing mode to enable default tenant_id fallback"""
    old_value = os.environ.get("TESTING")
    os.environ["TESTING"] = "1"
    yield
    if old_value is not None:
        os.environ["TESTING"] = old_value
    else:
        os.environ.pop("TESTING", None)


@pytest.fixture(autouse=True)
def mock_tenant_context():
    """Auto-mock tenant context for all tests"""
    with patch("src.core.middleware.tenant_context.get_tenant_id", return_value=1):
        yield


@pytest.fixture
def mock_async_session():
    """Create mock async database session"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    # Make it work as async context manager
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    return session


@pytest.fixture
def mock_agent():
    """Create a mock agent with standard properties"""
    agent = Mock(spec=Agent)
    agent.agent_id = "test-agent-123"
    agent.agent_type = AgentType.EXECUTOR
    agent.address = "http://localhost:8001"

    # Mock get_capabilities as async - with full field list
    async def mock_get_capabilities():
        return [
            AgentCapability(
                name="execute_code",
                description="Execute Python code",
                input_types=["code"],
                output_types=["result"],
            ),
            AgentCapability(
                name="run_tests",
                description="Run unit tests",
                input_types=["test_path"],
                output_types=["test_result"],
            ),
        ]

    agent.get_capabilities = mock_get_capabilities

    # Mock process_task
    async def mock_process_task(task: TaskData):
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data={"result": "completed"},
            execution_time=0.5,
        )

    agent.process_task = mock_process_task
    agent.tenant_id = 1

    return agent


@pytest.fixture
def agent_registry(mock_async_session):
    """Create AgentRegistry instance with mock database"""
    registry = AgentRegistry(db_session=mock_async_session)
    return registry


class TestAgentRegistryInitialization:
    """Test AgentRegistry initialization"""

    def test_init_creates_empty_collections(self):
        """Test initialization creates empty collections"""
        registry = AgentRegistry()

        assert registry._agents == {}
        assert len(registry._agents_by_type) == 0
        assert len(registry._agent_capabilities) == 0
        assert registry._active_tasks == {}
        assert registry._task_queue == []

    def test_init_with_db_session(self, mock_async_session):
        """Test initialization with database session"""
        registry = AgentRegistry(db_session=mock_async_session)

        assert registry._db_session == mock_async_session


class TestAgentRegistration:
    """Test agent registration functionality"""

    @pytest.mark.asyncio
    async def test_register_new_agent_success(self, agent_registry, mock_agent, mock_async_session):
        """Test successfully registering a new agent"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result

        # Act
        success = await agent_registry.register_agent(mock_agent)

        # Assert
        assert success is True
        assert mock_agent.agent_id in agent_registry._agents
        assert mock_agent.agent_id in agent_registry._agents_by_type[AgentType.EXECUTOR]
        assert "execute_code" in agent_registry._agent_capabilities[mock_agent.agent_id]
        assert "run_tests" in agent_registry._agent_capabilities[mock_agent.agent_id]

    @pytest.mark.asyncio
    async def test_register_agent_adds_to_cache(
        self, agent_registry, mock_agent, mock_async_session
    ):
        """Test registered agent is added to local cache"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result

        # Act
        await agent_registry.register_agent(mock_agent)

        # Assert
        cached_agent = agent_registry._agents.get(mock_agent.agent_id)
        assert cached_agent is not None
        assert cached_agent.agent_id == mock_agent.agent_id


class TestGetAgentById:
    """Test get_agent_by_id method"""

    @pytest.mark.asyncio
    async def test_get_agent_by_id_exists(self, agent_registry, mock_agent, mock_async_session):
        """Test getting an agent that exists"""
        # Arrange - register agent first
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result
        await agent_registry.register_agent(mock_agent)

        # Act
        result = await agent_registry.get_agent_by_id(mock_agent.agent_id)

        # Assert
        assert result is not None
        assert result.agent_id == mock_agent.agent_id

    @pytest.mark.asyncio
    async def test_get_agent_by_id_not_exists(self, agent_registry):
        """Test getting an agent that doesnt exist"""
        # Act
        result = await agent_registry.get_agent_by_id("non-existent-agent")

        # Assert
        assert result is None


class TestGetAllAgents:
    """Test get_all_agents method"""

    @pytest.mark.asyncio
    async def test_get_all_agents_returns_list(self, agent_registry, mock_async_session):
        """Test getting all agents returns list"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_async_session.execute.return_value = mock_result

        # Act
        result = await agent_registry.get_all_agents(tenant_id=1)

        # Assert
        assert isinstance(result, list)


class TestGetAgentsByType:
    """Test get_agents_by_type method"""

    @pytest.mark.asyncio
    async def test_get_agents_by_type_returns_matching(
        self, agent_registry, mock_agent, mock_async_session
    ):
        """Test getting agents by type returns matching agents"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result
        await agent_registry.register_agent(mock_agent)

        # Act
        result = await agent_registry.get_agents_by_type(AgentType.EXECUTOR)

        # Assert
        assert len(result) == 1
        assert result[0].agent_id == mock_agent.agent_id

    @pytest.mark.asyncio
    async def test_get_agents_by_type_empty(self, agent_registry):
        """Test getting agents by type when none exist"""
        # Act
        result = await agent_registry.get_agents_by_type(AgentType.CVA)

        # Assert
        assert result == []


class TestGetAgentsWithCapability:
    """Test get_agents_with_capability method"""

    @pytest.mark.asyncio
    async def test_get_agents_with_capability_returns_matching(
        self, agent_registry, mock_agent, mock_async_session
    ):
        """Test getting agents with capability returns matching agents"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result
        await agent_registry.register_agent(mock_agent)

        # Act
        result = await agent_registry.get_agents_with_capability("execute_code")

        # Assert
        assert len(result) == 1
        assert result[0].agent_id == mock_agent.agent_id

    @pytest.mark.asyncio
    async def test_get_agents_with_capability_no_match(
        self, agent_registry, mock_agent, mock_async_session
    ):
        """Test getting agents with capability when no match"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result
        await agent_registry.register_agent(mock_agent)

        # Act
        result = await agent_registry.get_agents_with_capability("non_existent_capability")

        # Assert
        assert result == []


class TestFindBestAgentForTask:
    """Test find_best_agent_for_task method"""

    @pytest.mark.asyncio
    async def test_find_best_agent_returns_available_agent(
        self, agent_registry, mock_agent, mock_async_session
    ):
        """Test finding best agent returns available agent"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result
        await agent_registry.register_agent(mock_agent)

        # Register heartbeat to make agent healthy
        agent_registry._agent_health[mock_agent.agent_id] = datetime.now(timezone.utc)

        task = TaskData(
            id="task-123",
            title="Test Task",
            description="Test task description",
            priority=1,
            status="pending",
            metadata={"agent_type": "executor"},
        )

        # Act
        result = await agent_registry.find_best_agent_for_task(task)

        # Assert
        assert result is not None

    @pytest.mark.asyncio
    async def test_find_best_agent_no_available(self, agent_registry):
        """Test finding best agent when none available"""
        task = TaskData(
            id="task-123",
            title="Test Task",
            description="Test task description",
            priority=1,
            status="pending",
            metadata={},
        )

        # Act
        result = await agent_registry.find_best_agent_for_task(task)

        # Assert
        assert result is None


class TestDistributeTask:
    """Test distribute_task method"""

    @pytest.mark.asyncio
    async def test_distribute_task_success(self, agent_registry, mock_agent, mock_async_session):
        """Test distributing task to available agent"""
        # Arrange
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = Mock(return_value=None)
        mock_async_session.execute.return_value = mock_result
        await agent_registry.register_agent(mock_agent)

        # Register heartbeat to make agent healthy
        agent_registry._agent_health[mock_agent.agent_id] = datetime.now(timezone.utc)

        task = TaskData(
            id="task-123",
            title="Test Task",
            description="Test task description",
            priority=1,
            status="pending",
            metadata={"agent_type": "executor"},
        )

        # Act
        result = await agent_registry.distribute_task(task)

        # Assert
        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_distribute_task_no_agent(self, agent_registry):
        """Test distributing task when no agent available"""
        task = TaskData(
            id="task-123",
            title="Test Task",
            description="Test task description",
            priority=1,
            status="pending",
            metadata={},
        )

        # Act
        result = await agent_registry.distribute_task(task)

        # Assert
        assert result is not None
        assert result.success is False


class TestGetSystemStatus:
    """Test get_system_status method"""

    @pytest.mark.asyncio
    async def test_get_system_status_returns_dict(self, agent_registry):
        """Test getting system status returns dict"""
        # Act
        result = await agent_registry.get_system_status()

        # Assert
        assert isinstance(result, dict)
        assert "total_agents" in result
        assert "healthy_agents" in result
        assert "agents_by_type" in result


class TestMemoryLeakPrevention:
    """Test memory leak prevention features"""

    def test_max_task_queue_size_limit_set(self, agent_registry):
        """Test task queue size limit is set"""
        assert agent_registry._max_task_queue_size == 1000

    def test_max_completed_tasks_history_limit_set(self, agent_registry):
        """Test completed tasks history limit is set"""
        assert agent_registry._max_completed_tasks_history == 500


class TestShutdown:
    """Test shutdown method"""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_cleanup_task(self, agent_registry):
        """Test shutdown cancels background cleanup task"""

        # Arrange - create a real asyncio task that we can cancel
        async def dummy_task():
            await asyncio.sleep(1000)  # Long sleep, will be cancelled

        task = asyncio.create_task(dummy_task())
        agent_registry._cleanup_task = task

        # Act
        await agent_registry.shutdown()

        # Assert - task should be cancelled
        assert task.cancelled() or task.done()
