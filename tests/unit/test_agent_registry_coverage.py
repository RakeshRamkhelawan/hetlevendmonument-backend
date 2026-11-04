"""
Comprehensive tests for src/core/agents/agent_registry.py
Coverage target: 100% of agent registry functionality
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.agents.agent_registry import AgentRegistry
from src.core.shared.interfaces import (
    Agent,
    AgentCapability,
    AgentType,
    BaseAgent,
    ExecutionResult,
    TaskData,
)


# Mock Agent for testing
class MockAgent(BaseAgent):
    """Mock agent for testing"""

    def __init__(self, agent_id: str, agent_type: AgentType):
        super().__init__(agent_id, agent_type)
        self.address = f"http://localhost:8100/{agent_id}"
        self.tenant_id = 1

    async def process_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True)

    async def get_capabilities(self):
        return [
            AgentCapability(
                name="test_capability",
                description="Test capability",
                input_types=["text"],
                output_types=["text"],
                resource_requirements={},
            )
        ]

    async def initialize(self) -> bool:
        return True

    async def shutdown(self) -> None:
        pass


class TestAgentRegistryInitialization:
    """Test AgentRegistry initialization"""

    def test_initialization(self):
        """Test registry initialization"""
        registry = AgentRegistry()

        assert registry is not None
        assert len(registry._agents) == 0
        assert len(registry._agents_by_type) == 0

    def test_initialization_with_db_session(self):
        """Test registry initialization with DB session"""
        mock_session = Mock(spec=AsyncSession)
        registry = AgentRegistry(db_session=mock_session)

        assert registry._db_session == mock_session

    def test_initialization_sets_cleanup_limits(self):
        """Test initialization sets memory leak protection limits"""
        registry = AgentRegistry()

        assert registry._max_task_queue_size == 1000
        assert registry._max_completed_tasks_history == 500


class TestRegisterAgent:
    """Test register_agent method"""

    @pytest.mark.asyncio
    async def test_register_agent_success(self):
        """Test successful agent registration"""
        mock_repo = AsyncMock()
        mock_repo.get_registered_agent_by_agent_id = AsyncMock(return_value=None)
        mock_repo.register_agent = AsyncMock(side_effect=lambda r: r)

        os.environ["TESTING"] = "1"

        registry = AgentRegistry(repository=mock_repo)
        agent = MockAgent("agent-1", AgentType.SPECIALIST)

        result = await registry.register_agent(agent)

        assert result is True
        assert "agent-1" in registry._agents

        del os.environ["TESTING"]

    @pytest.mark.asyncio
    async def test_register_agent_stores_in_memory(self):
        """Test agent registration stores in memory cache"""
        mock_repo = AsyncMock()
        mock_repo.get_registered_agent_by_agent_id = AsyncMock(return_value=None)
        mock_repo.register_agent = AsyncMock(side_effect=lambda r: r)

        os.environ["TESTING"] = "1"

        registry = AgentRegistry(repository=mock_repo)
        agent = MockAgent("agent-2", AgentType.CVA)

        await registry.register_agent(agent)

        assert registry._agents["agent-2"] == agent
        assert "agent-2" in registry._agents_by_type[AgentType.CVA]

        del os.environ["TESTING"]

    @pytest.mark.asyncio
    async def test_register_agent_initializes_health(self):
        """Test agent registration initializes health tracking"""
        mock_repo = AsyncMock()
        mock_repo.get_registered_agent_by_agent_id = AsyncMock(return_value=None)
        mock_repo.register_agent = AsyncMock(side_effect=lambda r: r)

        os.environ["TESTING"] = "1"

        registry = AgentRegistry(repository=mock_repo)
        agent = MockAgent("agent-3", AgentType.SPECIALIST)

        await registry.register_agent(agent)

        assert "agent-3" in registry._agent_health
        assert "agent-3" in registry._agent_load
        assert registry._agent_load["agent-3"] == 0.0

        del os.environ["TESTING"]


class TestGetAgent:
    """Test get_agent_by_id method"""

    @pytest.mark.asyncio
    async def test_get_agent_by_id_found(self):
        """Test getting agent by ID when it exists"""
        registry = AgentRegistry()
        agent = MockAgent("agent-4", AgentType.SPECIALIST)
        registry._agents["agent-4"] = agent

        result = await registry.get_agent_by_id("agent-4")

        assert result == agent

    @pytest.mark.asyncio
    async def test_get_agent_by_id_not_found(self):
        """Test getting agent by ID when it doesn't exist"""
        registry = AgentRegistry()

        result = await registry.get_agent_by_id("nonexistent")

        assert result is None


class TestGetAllAgents:
    """Test get_all_agents method"""

    @pytest.mark.asyncio
    async def test_get_all_agents_empty(self):
        """Test getting all agents when registry is empty"""
        mock_repo = AsyncMock()
        mock_repo.get_registered_agents = AsyncMock(return_value=[])

        registry = AgentRegistry(repository=mock_repo)
        agents = await registry.get_all_agents(tenant_id=1)

        assert agents == []

    @pytest.mark.asyncio
    async def test_get_all_agents_with_data(self):
        """Test getting all agents with data"""
        from unittest.mock import Mock

        mock_db_agent = Mock()
        mock_db_agent.agent_id = "agent-5"
        mock_db_agent.name = None
        mock_db_agent.description = None
        mock_db_agent.address = "http://localhost:8100/agent-5"
        mock_db_agent.capabilities = {"test": "capability"}
        mock_db_agent.last_heartbeat = datetime.now(timezone.utc)
        mock_db_agent.created_at = datetime.now(timezone.utc)
        mock_db_agent.updated_at = datetime.now(timezone.utc)

        mock_repo = AsyncMock()
        mock_repo.get_registered_agents = AsyncMock(return_value=[mock_db_agent])

        registry = AgentRegistry(repository=mock_repo)
        agents = await registry.get_all_agents(tenant_id=1)

        assert len(agents) == 1
        assert agents[0]["agent_id"] == "agent-5"


class TestFindBestAgent:
    """Test find_best_agent_for_task method"""

    @pytest.mark.asyncio
    async def test_find_best_agent_with_preferred_id(self):
        """Test finding agent with preferred agent ID"""
        registry = AgentRegistry()
        agent = MockAgent("agent-6", AgentType.SPECIALIST)
        registry._agents["agent-6"] = agent
        registry._agent_health["agent-6"] = datetime.now(timezone.utc)

        task = TaskData(
            id="task-1",
            title="Test",
            description="Test description",
            metadata={"agent_id": "agent-6"},
        )

        result = await registry.find_best_agent_for_task(task)

        assert result == agent

    @pytest.mark.asyncio
    async def test_find_best_agent_by_type(self):
        """Test finding agent by type"""
        registry = AgentRegistry()
        agent = MockAgent("agent-7", AgentType.CVA)
        registry._agents["agent-7"] = agent
        registry._agents_by_type[AgentType.CVA].append("agent-7")
        registry._agent_health["agent-7"] = datetime.now(timezone.utc)
        registry._agent_load["agent-7"] = 0.0
        registry._agent_stats["agent-7"] = {"tasks_completed": 10, "tasks_failed": 0}

        task = TaskData(
            id="task-2",
            title="Test",
            description="Test description",
            metadata={"agent_type": "cva"},
        )

        result = await registry.find_best_agent_for_task(task)

        assert result == agent

    @pytest.mark.asyncio
    async def test_find_best_agent_no_candidates(self):
        """Test finding agent when no candidates available"""
        registry = AgentRegistry()

        task = TaskData(id="task-3", title="Test", description="Test description", metadata={})

        result = await registry.find_best_agent_for_task(task)

        assert result is None


class TestDistributeTask:
    """Test distribute_task method"""

    @pytest.mark.asyncio
    async def test_distribute_task_success(self):
        """Test successful task distribution"""
        registry = AgentRegistry()
        agent = MockAgent("agent-8", AgentType.SPECIALIST)
        registry._agents["agent-8"] = agent
        registry._agents_by_type[AgentType.SPECIALIST].append("agent-8")
        registry._agent_health["agent-8"] = datetime.now(timezone.utc)
        registry._agent_load["agent-8"] = 0.0
        registry._agent_stats["agent-8"] = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_execution_time": 0.0,
        }

        task = TaskData(id="task-4", title="Test", description="Test description", metadata={})

        result = await registry.distribute_task(task)

        assert result is not None
        assert result.success is True

    @pytest.mark.asyncio
    async def test_distribute_task_no_agent(self):
        """Test task distribution when no agent available"""
        registry = AgentRegistry()

        task = TaskData(id="task-5", title="Test", description="Test description", metadata={})

        result = await registry.distribute_task(task)

        assert result is not None
        assert result.success is False
        assert "No suitable agent" in result.error_message

    @pytest.mark.asyncio
    async def test_distribute_task_updates_stats(self):
        """Test task distribution updates agent stats"""
        registry = AgentRegistry()
        agent = MockAgent("agent-9", AgentType.SPECIALIST)
        registry._agents["agent-9"] = agent
        registry._agents_by_type[AgentType.SPECIALIST].append("agent-9")
        registry._agent_health["agent-9"] = datetime.now(timezone.utc)
        registry._agent_load["agent-9"] = 0.0
        registry._agent_stats["agent-9"] = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_execution_time": 0.0,
        }

        task = TaskData(id="task-6", title="Test", description="Test description", metadata={})

        await registry.distribute_task(task)

        assert registry._agent_stats["agent-9"]["tasks_completed"] == 1


class TestGetAgentsByType:
    """Test get_agents_by_type method"""

    @pytest.mark.asyncio
    async def test_get_agents_by_type(self):
        """Test getting agents by type"""
        registry = AgentRegistry()
        agent1 = MockAgent("agent-10", AgentType.CVA)
        agent2 = MockAgent("agent-11", AgentType.CVA)

        registry._agents["agent-10"] = agent1
        registry._agents["agent-11"] = agent2
        registry._agents_by_type[AgentType.CVA] = ["agent-10", "agent-11"]

        agents = await registry.get_agents_by_type(AgentType.CVA)

        assert len(agents) == 2
        assert agent1 in agents
        assert agent2 in agents


class TestGetAgentsWithCapability:
    """Test get_agents_with_capability method"""

    @pytest.mark.asyncio
    async def test_get_agents_with_capability(self):
        """Test getting agents with specific capability"""
        registry = AgentRegistry()
        agent = MockAgent("agent-12", AgentType.SPECIALIST)

        registry._agents["agent-12"] = agent
        registry._agent_capabilities["agent-12"] = {
            "test_capability",
            "other_capability",
        }

        agents = await registry.get_agents_with_capability("test_capability")

        assert len(agents) == 1
        assert agents[0] == agent

    @pytest.mark.asyncio
    async def test_get_agents_with_capability_none(self):
        """Test getting agents when none have capability"""
        registry = AgentRegistry()
        agent = MockAgent("agent-13", AgentType.SPECIALIST)

        registry._agents["agent-13"] = agent
        registry._agent_capabilities["agent-13"] = {"other_capability"}

        agents = await registry.get_agents_with_capability("nonexistent")

        assert len(agents) == 0


class TestGetSystemStatus:
    """Test get_system_status method"""

    @pytest.mark.asyncio
    async def test_get_system_status(self):
        """Test getting system status"""
        registry = AgentRegistry()
        agent = MockAgent("agent-14", AgentType.SPECIALIST)

        registry._agents["agent-14"] = agent
        registry._agent_health["agent-14"] = datetime.now(timezone.utc)
        registry._agent_load["agent-14"] = 0.5
        registry._agent_stats["agent-14"] = {"tasks_completed": 10, "tasks_failed": 2}

        status = await registry.get_system_status()

        assert status["total_agents"] == 1
        assert status["healthy_agents"] == 1
        assert status["tasks_completed"] == 10
        assert status["tasks_failed"] == 2

    @pytest.mark.asyncio
    async def test_get_system_status_calculates_success_rate(self):
        """Test system status calculates success rate"""
        registry = AgentRegistry()

        registry._agent_stats["agent-15"] = {"tasks_completed": 8, "tasks_failed": 2}

        status = await registry.get_system_status()

        assert status["success_rate"] == 80.0


class TestAgentHealth:
    """Test _is_agent_healthy method"""

    @pytest.mark.asyncio
    async def test_is_agent_healthy_true(self):
        """Test agent health check returns True for healthy agent"""
        registry = AgentRegistry()
        registry._agent_health["agent-16"] = datetime.now(timezone.utc)

        result = await registry._is_agent_healthy("agent-16")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_agent_healthy_false_old(self):
        """Test agent health check returns False for old heartbeat"""
        registry = AgentRegistry()
        registry._agent_health["agent-17"] = datetime.now(timezone.utc) - timedelta(minutes=10)

        result = await registry._is_agent_healthy("agent-17")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_agent_healthy_false_missing(self):
        """Test agent health check returns False for missing agent"""
        registry = AgentRegistry()

        result = await registry._is_agent_healthy("nonexistent")

        assert result is False


class TestEventEmission:
    """Test _emit_event method"""

    @pytest.mark.asyncio
    async def test_emit_event_no_callbacks(self):
        """Test emitting event with no callbacks"""
        registry = AgentRegistry()

        # Should not raise
        await registry._emit_event("test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_event_with_callback(self):
        """Test emitting event with callback"""
        registry = AgentRegistry()
        callback = AsyncMock()
        registry._event_callbacks["test_event"].append(callback)

        await registry._emit_event("test_event", {"key": "value"})

        callback.assert_called_once_with({"key": "value"})


class TestMemoryCleanup:
    """Test memory leak prevention methods"""

    @pytest.mark.asyncio
    async def test_start_background_cleanup(self):
        """Test starting background cleanup task"""
        registry = AgentRegistry()

        await registry.start_background_cleanup()

        assert registry._cleanup_task is not None
        assert not registry._cleanup_task.done()

        # Cleanup
        await registry.shutdown()

    @pytest.mark.asyncio
    async def test_remove_agent(self):
        """Test removing agent"""
        mock_repo = AsyncMock()
        mock_repo.delete_agent = AsyncMock()

        registry = AgentRegistry(tenant_id=1, repository=mock_repo)
        agent = MockAgent("agent-18", AgentType.SPECIALIST)

        registry._agents["agent-18"] = agent
        registry._agents_by_type[AgentType.SPECIALIST].append("agent-18")
        registry._agent_health["agent-18"] = datetime.now(timezone.utc)
        registry._agent_load["agent-18"] = 0.0

        await registry._remove_agent("agent-18")

        assert "agent-18" not in registry._agents
        assert "agent-18" not in registry._agent_health


class TestTenantContextErrors:
    """Test tenant context error paths in register_agent"""

    @pytest.mark.asyncio
    async def test_register_agent_returns_false_without_tenant_context(self):
        """register_agent must return False when no tenant context exists outside test mode.

        RuntimeError is raised internally and caught by register_agent's own error handler,
        which logs it and returns False. The caller sees False, not an exception.
        """
        mock_repo = AsyncMock()
        mock_repo.get_registered_agent_by_agent_id = AsyncMock(return_value=None)

        registry = AgentRegistry(repository=mock_repo)
        agent = MockAgent("agent-no-tenant", AgentType.SPECIALIST)

        saved = os.environ.pop("TESTING", None)
        try:
            result = await registry.register_agent(agent)
            assert result is False, (
                "register_agent must return False when tenant context is missing outside test mode"
            )
        finally:
            if saved is not None:
                os.environ["TESTING"] = saved


class TestShutdown:
    """Test shutdown method"""

    @pytest.mark.asyncio
    async def test_shutdown_cancels_cleanup_task(self):
        """Test shutdown cancels cleanup task"""
        registry = AgentRegistry()

        await registry.start_background_cleanup()
        await registry.shutdown()

        assert registry._cleanup_task.done()
