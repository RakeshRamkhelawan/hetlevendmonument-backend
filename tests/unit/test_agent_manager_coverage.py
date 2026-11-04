"""
Unit Tests for Agent Manager - P4.1.5
Tests for src/core/subagents/agent_manager.py

Coverage target: 80%+

Tests:
- AgentManager initialization and agent type registration
- Task submission and queue management
- Agent selection and scoring algorithms
- Task execution lifecycle
- Management loop and health checks
- Auto-scaling behavior
- Performance metrics collection
- AgentAllocation dataclass
- Global singleton pattern
"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Mock the agent_factory before importing agent_manager
with patch("src.core.subagents.agent_manager.AgentFactory") as MockFactory:
    mock_factory_instance = MagicMock()
    mock_factory_instance.register_agent_type = MagicMock()
    mock_factory_instance.register_default_configuration = MagicMock()
    mock_factory_instance.active_agents = {}
    mock_factory_instance.create_agent = AsyncMock(return_value="agent_123")
    mock_factory_instance.get_agent = AsyncMock()
    mock_factory_instance.find_capable_agents = AsyncMock(return_value=[])
    mock_factory_instance.shutdown_all_agents = AsyncMock()
    mock_factory_instance.get_factory_status = MagicMock(return_value={})
    MockFactory.return_value = mock_factory_instance

    from src.core.subagents.agent_manager import (
        AgentManager,
        AgentAllocation,
        create_agent_manager,
        get_agent_manager,
    )

from src.core.subagents.agent_factory import AgentConfiguration, AgentType, BaseAgent


@pytest.fixture(autouse=True)
def reset_agent_manager_singleton():
    """Reset the global singleton before each test"""
    import src.core.subagents.agent_manager as module

    module._agent_manager = None
    yield
    module._agent_manager = None


class TestAgentAllocation:
    """Test AgentAllocation dataclass"""

    def test_create_agent_allocation(self):
        """Test AgentAllocation creation with all fields"""
        allocation = AgentAllocation(
            agent_id="agent_001",
            task_id="task_001",
            allocated_at=datetime.now(timezone.utc),
            estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=5),
            priority=1,
        )

        assert allocation.agent_id == "agent_001"
        assert allocation.task_id == "task_001"
        assert allocation.priority == 1
        assert allocation.estimated_completion > allocation.allocated_at

    def test_agent_allocation_to_dict(self):
        """Test conversion to dictionary"""
        now = datetime.now(timezone.utc)
        allocation = AgentAllocation(
            agent_id="agent_002",
            task_id="task_002",
            allocated_at=now,
            estimated_completion=now + timedelta(seconds=60),
            priority=3,
        )

        allocation_dict = asdict(allocation)
        assert allocation_dict["agent_id"] == "agent_002"
        assert allocation_dict["priority"] == 3


class TestAgentManager:
    """Test AgentManager class"""

    @pytest.fixture
    def mock_agent_factory(self):
        """Create mock agent factory"""
        factory = MagicMock()
        factory.register_agent_type = MagicMock()
        factory.register_default_configuration = MagicMock()
        factory.active_agents = {}
        factory.create_agent = AsyncMock(return_value="agent_123")
        factory.get_agent = AsyncMock()
        factory.find_capable_agents = AsyncMock(return_value=[])
        factory.shutdown_all_agents = AsyncMock()
        factory.get_factory_status = MagicMock(return_value={"status": "ok"})
        return factory

    @pytest.fixture
    def agent_manager(self, mock_agent_factory):
        """Create agent manager with mocked factory"""
        manager = AgentManager(mock_agent_factory)
        return manager

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent"""
        agent = MagicMock(spec=BaseAgent)
        agent.agent_id = "agent_test_001"
        agent.current_tasks = {}
        agent.capabilities = {"data_analysis", "statistical_analysis"}
        agent.status = MagicMock()
        agent.status.value = "active"

        # Mock config
        agent.config = MagicMock(spec=AgentConfiguration)
        agent.config.agent_type = AgentType.DATA_ANALYSIS
        agent.config.max_concurrent_tasks = 3
        agent.config.health_check_interval = 60

        # Mock metrics
        agent.metrics = MagicMock()
        agent.metrics.tasks_completed = 10
        agent.metrics.tasks_failed = 2
        agent.metrics.average_execution_time = 5.5

        # Mock execute_task
        agent.execute_task = AsyncMock(
            return_value={
                "success": True,
                "result": {"data": "test"},
                "execution_time": 2.5,
            }
        )

        # Mock health_check
        agent.health_check = AsyncMock(return_value={"health": "healthy"})

        return agent

    def test_agent_manager_initialization(self, agent_manager, mock_agent_factory):
        """Test agent manager initializes with correct state"""
        assert agent_manager.agent_factory == mock_agent_factory
        assert agent_manager.agent_allocations == {}
        assert agent_manager.task_queue == []
        assert agent_manager.completed_tasks == []
        assert agent_manager.agent_health_checks == {}
        assert agent_manager.performance_metrics == {}
        assert agent_manager.running is False
        assert agent_manager.management_task is None

    def test_register_agent_types(self, agent_manager, mock_agent_factory):
        """Test agent types are registered on initialization"""
        # Verify register_agent_type was called for all agent types
        assert mock_agent_factory.register_agent_type.call_count >= 6

    def test_register_default_configurations(self, agent_manager, mock_agent_factory):
        """Test default configurations are registered"""
        # Verify register_default_configuration was called
        assert mock_agent_factory.register_default_configuration.call_count >= 6

    @pytest.mark.asyncio
    async def test_start_manager(self, agent_manager, mock_agent_factory):
        """Test starting the agent manager"""
        mock_agent_factory.create_agent = AsyncMock(return_value="agent_id")

        await agent_manager.start_manager()

        assert agent_manager.running is True
        assert agent_manager.management_task is not None

        # Clean up
        await agent_manager.stop_manager()

    @pytest.mark.asyncio
    async def test_start_manager_already_running(self, agent_manager, mock_agent_factory):
        """Test starting already running manager"""
        agent_manager.running = True

        await agent_manager.start_manager()

        # Should not create duplicate task
        assert agent_manager.management_task is None

    @pytest.mark.asyncio
    async def test_stop_manager(self, agent_manager, mock_agent_factory):
        """Test stopping the agent manager"""
        agent_manager.running = True
        agent_manager.management_task = asyncio.create_task(asyncio.sleep(100))

        await agent_manager.stop_manager()

        assert agent_manager.running is False
        mock_agent_factory.shutdown_all_agents.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_initial_agent_pool(self, agent_manager, mock_agent_factory):
        """Test creation of initial agent pool"""
        mock_agent_factory.create_agent = AsyncMock(return_value="agent_id")

        await agent_manager._create_initial_agent_pool()

        # Should create multiple agents
        assert mock_agent_factory.create_agent.call_count >= 4

    @pytest.mark.asyncio
    async def test_submit_task(self, agent_manager, mock_agent_factory):
        """Test task submission"""
        task_data = {
            "name": "test_task",
            "required_capabilities": ["data_analysis"],
        }

        task_id = await agent_manager.submit_task(task_data)

        assert task_id is not None
        assert task_id.startswith("task_")
        assert len(agent_manager.task_queue) == 1
        assert agent_manager.task_queue[0]["status"] == "queued"

    @pytest.mark.asyncio
    async def test_submit_task_with_id(self, agent_manager, mock_agent_factory):
        """Test task submission with provided ID"""
        task_data = {
            "id": "custom_task_id",
            "name": "test_task",
        }

        task_id = await agent_manager.submit_task(task_data)

        assert task_id == "custom_task_id"

    @pytest.mark.asyncio
    async def test_try_assign_tasks_empty_queue(self, agent_manager):
        """Test task assignment with empty queue"""
        await agent_manager._try_assign_tasks()
        # Should complete without error
        assert len(agent_manager.task_queue) == 0

    @pytest.mark.asyncio
    async def test_try_assign_tasks_no_capable_agents(self, agent_manager, mock_agent_factory):
        """Test task assignment when no capable agents exist"""
        agent_manager.task_queue = [
            {
                "id": "task_001",
                "required_capabilities": ["rare_capability"],
            }
        ]
        mock_agent_factory.find_capable_agents = AsyncMock(return_value=[])

        await agent_manager._try_assign_tasks()

        # Task should remain in queue
        assert len(agent_manager.task_queue) == 1

    @pytest.mark.asyncio
    async def test_try_assign_tasks_with_capable_agent(
        self, agent_manager, mock_agent_factory, mock_agent
    ):
        """Test task assignment when capable agents exist"""
        agent_manager.task_queue = [
            {
                "id": "task_001",
                "required_capabilities": ["data_analysis"],
            }
        ]
        mock_agent_factory.find_capable_agents = AsyncMock(return_value=["agent_001"])
        mock_agent_factory.get_agent = AsyncMock(return_value=mock_agent)

        await agent_manager._try_assign_tasks()

        # Task should be removed from queue and assigned
        assert len(agent_manager.task_queue) == 0

    @pytest.mark.asyncio
    async def test_select_best_agent(self, agent_manager, mock_agent_factory, mock_agent):
        """Test best agent selection algorithm"""
        mock_agent_factory.get_agent = AsyncMock(return_value=mock_agent)

        candidate_agents = ["agent_001", "agent_002"]
        task_data = {"required_capabilities": ["data_analysis"]}

        best_agent = await agent_manager._select_best_agent(candidate_agents, task_data)

        assert best_agent is not None

    @pytest.mark.asyncio
    async def test_select_best_agent_no_agents(self, agent_manager, mock_agent_factory):
        """Test best agent selection with no available agents"""
        mock_agent_factory.get_agent = AsyncMock(return_value=None)

        best_agent = await agent_manager._select_best_agent(["agent_001"], {})

        assert best_agent is None

    @pytest.mark.asyncio
    async def test_calculate_agent_score(self, agent_manager, mock_agent):
        """Test agent scoring algorithm"""
        task_data = {"required_capabilities": ["data_analysis"]}

        score = await agent_manager._calculate_agent_score(mock_agent, task_data)

        assert score > 0
        # Score should be reasonable (sum of load, success rate, speed, capability match)
        assert score <= 100

    @pytest.mark.asyncio
    async def test_calculate_agent_score_zero_tasks(self, agent_manager, mock_agent):
        """Test agent scoring with zero completed tasks"""
        mock_agent.metrics.tasks_completed = 0
        mock_agent.metrics.tasks_failed = 0
        task_data = {"required_capabilities": []}

        score = await agent_manager._calculate_agent_score(mock_agent, task_data)

        assert score >= 0

    @pytest.mark.asyncio
    async def test_calculate_agent_score_high_load(self, agent_manager, mock_agent):
        """Test agent scoring with high load"""
        mock_agent.current_tasks = {"t1": {}, "t2": {}, "t3": {}}  # Full capacity
        task_data = {"required_capabilities": ["data_analysis"]}

        score = await agent_manager._calculate_agent_score(mock_agent, task_data)

        # Score should be lower due to high load
        assert score < 100

    @pytest.mark.asyncio
    async def test_assign_task_to_agent(self, agent_manager, mock_agent_factory, mock_agent):
        """Test task assignment to specific agent"""
        mock_agent_factory.get_agent = AsyncMock(return_value=mock_agent)

        task_data = {
            "id": "task_001",
            "name": "test_task",
            "estimated_duration": 60,
            "priority": 2,
        }

        await agent_manager._assign_task_to_agent(task_data, "agent_001")

        assert task_data["status"] == "assigned"
        assert task_data["assigned_to"] == "agent_001"
        assert "task_001" in agent_manager.agent_allocations

    @pytest.mark.asyncio
    async def test_assign_task_agent_not_found(self, agent_manager, mock_agent_factory):
        """Test task assignment when agent not found"""
        mock_agent_factory.get_agent = AsyncMock(return_value=None)

        task_data = {"id": "task_001", "name": "test_task"}

        await agent_manager._assign_task_to_agent(task_data, "nonexistent_agent")

        # Task should not be in allocations
        assert "task_001" not in agent_manager.agent_allocations

    @pytest.mark.asyncio
    async def test_execute_task_on_agent_success(self, agent_manager, mock_agent):
        """Test successful task execution on agent"""
        task_data = {
            "id": "task_001",
            "name": "test_task",
        }
        agent_manager.agent_allocations["task_001"] = AgentAllocation(
            agent_id="agent_001",
            task_id="task_001",
            allocated_at=datetime.now(timezone.utc),
            estimated_completion=datetime.now(timezone.utc) + timedelta(seconds=60),
            priority=1,
        )

        await agent_manager._execute_task_on_agent(task_data, mock_agent)

        assert task_data["status"] == "completed"
        assert "task_001" not in agent_manager.agent_allocations
        assert len(agent_manager.completed_tasks) == 1

    @pytest.mark.asyncio
    async def test_execute_task_on_agent_failure(self, agent_manager, mock_agent):
        """Test failed task execution on agent"""
        mock_agent.execute_task = AsyncMock(
            return_value={
                "success": False,
                "error": "Test error",
            }
        )

        task_data = {"id": "task_002", "name": "failing_task"}

        await agent_manager._execute_task_on_agent(task_data, mock_agent)

        assert task_data["status"] == "failed"

    @pytest.mark.asyncio
    async def test_execute_task_on_agent_exception(self, agent_manager, mock_agent):
        """Test task execution with exception"""
        mock_agent.execute_task = AsyncMock(side_effect=Exception("Execution error"))

        task_data = {"id": "task_003", "name": "exception_task"}

        await agent_manager._execute_task_on_agent(task_data, mock_agent)

        assert task_data["status"] == "failed"
        assert "error" in task_data

    @pytest.mark.asyncio
    async def test_execute_task_trims_completed_tasks(self, agent_manager, mock_agent):
        """Test that completed tasks list is trimmed to 1000"""
        agent_manager.completed_tasks = [{"id": f"old_task_{i}"} for i in range(1001)]
        task_data = {"id": "new_task", "name": "test"}

        await agent_manager._execute_task_on_agent(task_data, mock_agent)

        assert len(agent_manager.completed_tasks) == 1000

    @pytest.mark.asyncio
    async def test_perform_health_checks(self, agent_manager, mock_agent_factory, mock_agent):
        """Test health check execution"""
        mock_agent_factory.active_agents = {"agent_001": mock_agent}
        agent_manager.agent_health_checks = {}

        await agent_manager._perform_health_checks()

        assert "agent_001" in agent_manager.agent_health_checks
        mock_agent.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_health_checks_skip_recent(
        self, agent_manager, mock_agent_factory, mock_agent
    ):
        """Test health check skips recently checked agents"""
        mock_agent_factory.active_agents = {"agent_001": mock_agent}
        agent_manager.agent_health_checks = {"agent_001": datetime.now(timezone.utc)}

        await agent_manager._perform_health_checks()

        # Should not call health_check again (too recent)
        mock_agent.health_check.assert_not_called()

    @pytest.mark.asyncio
    async def test_perform_health_checks_unhealthy(
        self, agent_manager, mock_agent_factory, mock_agent
    ):
        """Test health check logs unhealthy agents"""
        mock_agent.health_check = AsyncMock(return_value={"health": "degraded"})
        mock_agent_factory.active_agents = {"agent_001": mock_agent}
        agent_manager.agent_health_checks = {}

        await agent_manager._perform_health_checks()

        mock_agent.health_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_perform_health_checks_exception(
        self, agent_manager, mock_agent_factory, mock_agent
    ):
        """Test health check handles exceptions"""
        mock_agent.health_check = AsyncMock(side_effect=Exception("Health check failed"))
        mock_agent_factory.active_agents = {"agent_001": mock_agent}
        agent_manager.agent_health_checks = {}

        # Should not raise
        await agent_manager._perform_health_checks()

    @pytest.mark.asyncio
    async def test_update_performance_metrics(self, agent_manager, mock_agent_factory):
        """Test performance metrics update"""
        mock_agent_factory.active_agents = {"agent_001": MagicMock()}
        agent_manager.agent_allocations = {"task_001": MagicMock()}
        agent_manager.task_queue = [{"id": "task_002"}]
        agent_manager.completed_tasks = [
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
                "execution_time": 5,
            },
            {
                "status": "completed",
                "completed_at": datetime.now(timezone.utc),
                "execution_time": 3,
            },
            {"status": "failed", "completed_at": datetime.now(timezone.utc), "execution_time": 1},
        ]

        await agent_manager._update_performance_metrics()

        assert "total_agents" in agent_manager.performance_metrics
        assert agent_manager.performance_metrics["total_agents"] == 1
        assert agent_manager.performance_metrics["active_allocations"] == 1
        assert agent_manager.performance_metrics["queued_tasks"] == 1
        assert agent_manager.performance_metrics["recent_success_rate"] > 0

    @pytest.mark.asyncio
    async def test_update_performance_metrics_empty(self, agent_manager, mock_agent_factory):
        """Test performance metrics with no data"""
        mock_agent_factory.active_agents = {}
        agent_manager.agent_allocations = {}
        agent_manager.task_queue = []
        agent_manager.completed_tasks = []

        await agent_manager._update_performance_metrics()

        assert agent_manager.performance_metrics["total_agents"] == 0
        assert agent_manager.performance_metrics["recent_success_rate"] == 100

    @pytest.mark.asyncio
    async def test_handle_auto_scaling_scale_up(self, agent_manager, mock_agent_factory):
        """Test auto-scaling triggers scale up"""
        agent_manager.task_queue = [{"required_capabilities": ["data_analysis"]} for _ in range(15)]
        agent_manager.performance_metrics = {"system_utilization": 90}
        mock_agent_factory.active_agents = {}
        mock_agent_factory.create_agent = AsyncMock(return_value="new_agent")

        await agent_manager._handle_auto_scaling()

        # Should attempt to create agents
        mock_agent_factory.create_agent.assert_called()

    @pytest.mark.asyncio
    async def test_handle_auto_scaling_no_scale_needed(self, agent_manager, mock_agent_factory):
        """Test auto-scaling when no scaling needed"""
        agent_manager.task_queue = []
        agent_manager.performance_metrics = {"system_utilization": 50}

        await agent_manager._handle_auto_scaling()

        # Should not create agents
        mock_agent_factory.create_agent.assert_not_called()

    def test_capability_to_agent_type(self, agent_manager):
        """Test capability to agent type mapping"""
        assert agent_manager._capability_to_agent_type("data_analysis") == AgentType.DATA_ANALYSIS
        assert (
            agent_manager._capability_to_agent_type("system_monitoring") == AgentType.SYSTEM_MONITOR
        )
        assert agent_manager._capability_to_agent_type("code_execution") == AgentType.CODE_EXECUTION
        assert agent_manager._capability_to_agent_type("unknown_capability") is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_allocations(self, agent_manager):
        """Test cleanup of expired allocations"""
        expired_time = datetime.now(timezone.utc) - timedelta(minutes=20)
        agent_manager.agent_allocations = {
            "expired_task": AgentAllocation(
                agent_id="agent_001",
                task_id="expired_task",
                allocated_at=expired_time,
                estimated_completion=expired_time + timedelta(minutes=5),
                priority=1,
            ),
            "active_task": AgentAllocation(
                agent_id="agent_002",
                task_id="active_task",
                allocated_at=datetime.now(timezone.utc),
                estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=5),
                priority=1,
            ),
        }

        await agent_manager._cleanup_expired_allocations()

        assert "expired_task" not in agent_manager.agent_allocations
        assert "active_task" in agent_manager.agent_allocations

    def test_get_manager_status(self, agent_manager, mock_agent_factory, mock_agent):
        """Test getting manager status"""
        mock_agent_factory.active_agents = {"agent_001": mock_agent}
        agent_manager.running = True
        agent_manager.performance_metrics = {"test": "data"}
        agent_manager.task_queue = [{"id": "task_001"}]

        status = agent_manager.get_manager_status()

        assert status["manager_running"] is True
        assert status["task_queue_size"] == 1
        assert "agents" in status
        assert "agent_001" in status["agents"]

    def test_get_manager_status_empty(self, agent_manager, mock_agent_factory):
        """Test getting manager status when empty"""
        mock_agent_factory.active_agents = {}
        agent_manager.running = False

        status = agent_manager.get_manager_status()

        assert status["manager_running"] is False
        assert status["agents"] == {}

    @pytest.mark.asyncio
    async def test_get_task_status_in_queue(self, agent_manager):
        """Test getting task status from queue"""
        agent_manager.task_queue = [{"id": "queued_task", "status": "queued"}]

        status = await agent_manager.get_task_status("queued_task")

        assert status is not None
        assert status["id"] == "queued_task"
        assert status["status"] == "queued"

    @pytest.mark.asyncio
    async def test_get_task_status_in_allocation(self, agent_manager):
        """Test getting task status from allocations"""
        agent_manager.agent_allocations = {
            "executing_task": AgentAllocation(
                agent_id="agent_001",
                task_id="executing_task",
                allocated_at=datetime.now(timezone.utc),
                estimated_completion=datetime.now(timezone.utc) + timedelta(minutes=5),
                priority=1,
            )
        }

        status = await agent_manager.get_task_status("executing_task")

        assert status is not None
        assert status["id"] == "executing_task"
        assert status["status"] == "executing"

    @pytest.mark.asyncio
    async def test_get_task_status_completed(self, agent_manager):
        """Test getting task status from completed tasks"""
        agent_manager.completed_tasks = [
            {"id": "completed_task", "status": "completed", "result": "success"}
        ]

        status = await agent_manager.get_task_status("completed_task")

        assert status is not None
        assert status["id"] == "completed_task"
        assert status["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_task_status_not_found(self, agent_manager):
        """Test getting task status for unknown task"""
        status = await agent_manager.get_task_status("unknown_task")

        assert status is None


class TestGlobalAgentManager:
    """Test global agent manager singleton functions"""

    def test_create_agent_manager(self):
        """Test create_agent_manager creates instance"""
        # The function imports create_agent_factory locally, so we patch at the source module
        with patch("src.core.subagents.agent_factory.create_agent_factory") as mock_factory_fn:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            mock_factory_fn.return_value = mock_factory

            manager = create_agent_manager()

            assert manager is not None
            assert isinstance(manager, AgentManager)

    def test_create_agent_manager_singleton(self):
        """Test create_agent_manager returns same instance"""
        with patch("src.core.subagents.agent_factory.create_agent_factory") as mock_factory_fn:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            mock_factory_fn.return_value = mock_factory

            manager1 = create_agent_manager()
            manager2 = create_agent_manager()

            assert manager1 is manager2

    def test_get_agent_manager_none(self):
        """Test get_agent_manager returns None when not created"""
        import src.core.subagents.agent_manager as module

        module._agent_manager = None

        manager = get_agent_manager()

        assert manager is None

    def test_get_agent_manager_returns_instance(self):
        """Test get_agent_manager returns existing instance"""
        import src.core.subagents.agent_manager as module

        with patch("src.core.subagents.agent_factory.create_agent_factory") as mock_factory_fn:
            mock_factory = MagicMock()
            mock_factory.register_agent_type = MagicMock()
            mock_factory.register_default_configuration = MagicMock()
            mock_factory_fn.return_value = mock_factory

            create_agent_manager()
            manager = get_agent_manager()

            assert manager is not None


class TestManagementLoop:
    """Test management loop behavior"""

    @pytest.fixture
    def mock_agent_factory(self):
        """Create mock agent factory"""
        factory = MagicMock()
        factory.register_agent_type = MagicMock()
        factory.register_default_configuration = MagicMock()
        factory.active_agents = {}
        factory.create_agent = AsyncMock(return_value="agent_123")
        factory.get_agent = AsyncMock()
        factory.find_capable_agents = AsyncMock(return_value=[])
        factory.shutdown_all_agents = AsyncMock()
        factory.get_factory_status = MagicMock(return_value={})
        return factory

    @pytest.fixture
    def agent_manager(self, mock_agent_factory):
        """Create agent manager for testing"""
        return AgentManager(mock_agent_factory)

    @pytest.mark.asyncio
    async def test_management_loop_single_iteration(self, agent_manager, mock_agent_factory):
        """Test single iteration of management loop"""
        agent_manager.running = True
        mock_agent_factory.active_agents = {}

        # Run loop once
        async def run_one_iteration():
            await agent_manager._try_assign_tasks()
            await agent_manager._perform_health_checks()
            await agent_manager._update_performance_metrics()
            await agent_manager._handle_auto_scaling()
            await agent_manager._cleanup_expired_allocations()

        await run_one_iteration()

        # Should complete without error
        assert agent_manager.performance_metrics is not None

    @pytest.mark.asyncio
    async def test_management_loop_exception_handling(self, agent_manager, mock_agent_factory):
        """Test management loop handles exceptions gracefully"""
        agent_manager.running = True

        # Force an exception in try_assign_tasks
        original_try_assign = agent_manager._try_assign_tasks

        async def failing_try_assign():
            raise Exception("Test exception")

        agent_manager._try_assign_tasks = failing_try_assign

        # Should handle exception gracefully
        iteration_count = 0

        async def limited_loop():
            nonlocal iteration_count
            while agent_manager.running and iteration_count < 1:
                iteration_count += 1
                try:
                    await agent_manager._try_assign_tasks()
                except Exception:
                    pass  # Expected

        await limited_loop()

        # Restore original
        agent_manager._try_assign_tasks = original_try_assign


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.fixture
    def mock_agent_factory(self):
        """Create mock agent factory"""
        factory = MagicMock()
        factory.register_agent_type = MagicMock()
        factory.register_default_configuration = MagicMock()
        factory.active_agents = {}
        factory.create_agent = AsyncMock(return_value="agent_123")
        factory.get_agent = AsyncMock()
        factory.find_capable_agents = AsyncMock(return_value=[])
        factory.shutdown_all_agents = AsyncMock()
        factory.get_factory_status = MagicMock(return_value={})
        return factory

    @pytest.fixture
    def agent_manager(self, mock_agent_factory):
        """Create agent manager for edge case tests"""
        return AgentManager(mock_agent_factory)

    def test_capability_mapping_all_types(self, agent_manager):
        """Test all capability mappings"""
        mappings = [
            ("data_analysis", AgentType.DATA_ANALYSIS),
            ("statistical_analysis", AgentType.DATA_ANALYSIS),
            ("system_monitoring", AgentType.SYSTEM_MONITOR),
            ("resource_monitoring", AgentType.SYSTEM_MONITOR),
            ("code_execution", AgentType.CODE_EXECUTION),
            ("knowledge_search", AgentType.KNOWLEDGE_RETRIEVAL),
            ("report_generation", AgentType.REPORTING),
            ("performance_analysis", AgentType.PERFORMANCE_ANALYSIS),
        ]

        for capability, expected_type in mappings:
            result = agent_manager._capability_to_agent_type(capability)
            assert result == expected_type, f"Failed for {capability}"

    @pytest.mark.asyncio
    async def test_submit_multiple_tasks(self, agent_manager, mock_agent_factory):
        """Test submitting multiple tasks"""
        for i in range(10):
            task_id = await agent_manager.submit_task(
                {
                    "name": f"task_{i}",
                    "required_capabilities": ["data_analysis"],
                }
            )
            assert task_id is not None

        assert len(agent_manager.task_queue) == 10

    @pytest.mark.asyncio
    async def test_auto_scale_max_agents(self, agent_manager, mock_agent_factory):
        """Test auto-scaling respects max agent limit"""
        agent_manager.task_queue = [{"required_capabilities": ["data_analysis"]} for _ in range(20)]
        agent_manager.performance_metrics = {"system_utilization": 95}

        # Create mock agents at max capacity
        mock_agents = {}
        for i in range(3):
            mock_agent = MagicMock()
            mock_agent.config = MagicMock()
            mock_agent.config.agent_type = AgentType.DATA_ANALYSIS
            mock_agents[f"agent_{i}"] = mock_agent

        mock_agent_factory.active_agents = mock_agents

        await agent_manager._handle_auto_scaling()

        # Should not create more agents (already at max 3)
        mock_agent_factory.create_agent.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_score_with_zero_execution_time(self, agent_manager):
        """Test agent scoring with zero execution time"""
        mock_agent = MagicMock()
        mock_agent.current_tasks = {}
        mock_agent.capabilities = {"data_analysis"}
        mock_agent.config = MagicMock()
        mock_agent.config.max_concurrent_tasks = 3
        mock_agent.metrics = MagicMock()
        mock_agent.metrics.tasks_completed = 10
        mock_agent.metrics.tasks_failed = 0
        mock_agent.metrics.average_execution_time = 0

        score = await agent_manager._calculate_agent_score(mock_agent, {})

        assert score >= 0

    @pytest.mark.asyncio
    async def test_assign_task_exception(self, agent_manager, mock_agent_factory):
        """Test task assignment handles exceptions"""
        mock_agent_factory.get_agent = AsyncMock(side_effect=Exception("Database error"))

        task_data = {"id": "task_001", "name": "test"}

        # Should not raise
        await agent_manager._assign_task_to_agent(task_data, "agent_001")

        # Task should not be assigned
        assert "task_001" not in agent_manager.agent_allocations
