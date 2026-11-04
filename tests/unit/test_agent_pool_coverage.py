"""
Unit Tests for Agent Pool - P4.1.4
Tests for src/core/subagents/agent_pool.py

Coverage target: 80%+

Tests:
- PoolConfiguration dataclass
- PoolMetrics dataclass
- AgentPool initialization and configuration
- start_pool / stop_pool lifecycle
- Agent request and allocation
- Optimal agent selection
- Pool management loop
- Scaling up and down
- Pool metrics and analytics
- Global helper functions
"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# Import AgentType from the correct location
from src.core.subagents.agent_factory import AgentType

# Mock agent_manager and agent_factory before importing agent_pool
with patch("src.core.subagents.agent_pool.AgentManager") as MockAgentManager:
    mock_manager_instance = MagicMock()
    mock_factory_instance = MagicMock()
    mock_manager_instance.agent_factory = mock_factory_instance
    MockAgentManager.return_value = mock_manager_instance

    from src.core.subagents.agent_pool import (
        AgentPool,
        PoolConfiguration,
        PoolMetrics,
        create_agent_pool,
        get_agent_pool,
    )


@pytest.fixture(autouse=True)
def reset_agent_pool_singleton():
    """Reset the global singleton before each test"""
    import src.core.subagents.agent_pool as module

    module._agent_pool = None
    yield
    module._agent_pool = None


class TestPoolConfiguration:
    """Test PoolConfiguration dataclass"""

    def test_create_pool_configuration(self):
        """Test PoolConfiguration creation with all fields"""
        config = PoolConfiguration(
            min_agents_per_type={
                AgentType.SYSTEM_MONITOR: 1,
                AgentType.DATA_ANALYSIS: 2,
            },
            max_agents_per_type={
                AgentType.SYSTEM_MONITOR: 5,
                AgentType.DATA_ANALYSIS: 10,
            },
            scale_up_threshold=80.0,
            scale_down_threshold=20.0,
            scale_check_interval=30,
            idle_timeout=600,
        )

        assert config.min_agents_per_type[AgentType.SYSTEM_MONITOR] == 1
        assert config.min_agents_per_type[AgentType.DATA_ANALYSIS] == 2
        assert config.max_agents_per_type[AgentType.SYSTEM_MONITOR] == 5
        assert config.scale_up_threshold == 80.0
        assert config.scale_down_threshold == 20.0
        assert config.scale_check_interval == 30
        assert config.idle_timeout == 600

    def test_pool_configuration_to_dict(self):
        """Test PoolConfiguration can be converted to dict"""
        config = PoolConfiguration(
            min_agents_per_type={AgentType.REPORTING: 0},
            max_agents_per_type={AgentType.REPORTING: 3},
            scale_up_threshold=75.0,
            scale_down_threshold=25.0,
            scale_check_interval=60,
            idle_timeout=300,
        )

        config_dict = asdict(config)
        assert "min_agents_per_type" in config_dict
        assert "max_agents_per_type" in config_dict
        assert config_dict["scale_up_threshold"] == 75.0


class TestPoolMetrics:
    """Test PoolMetrics dataclass"""

    def test_create_pool_metrics_default(self):
        """Test PoolMetrics with default values"""
        metrics = PoolMetrics()

        assert metrics.total_agents == 0
        assert metrics.active_agents == 0
        assert metrics.idle_agents == 0
        assert metrics.busy_agents == 0
        assert metrics.total_capacity == 0
        assert metrics.current_utilization == 0.0
        assert metrics.scaling_events == 0
        assert metrics.last_scale_action is None

    def test_create_pool_metrics_custom(self):
        """Test PoolMetrics with custom values"""
        now = datetime.now(timezone.utc)
        metrics = PoolMetrics(
            total_agents=10,
            active_agents=5,
            idle_agents=3,
            busy_agents=2,
            total_capacity=50,
            current_utilization=65.5,
            scaling_events=15,
            last_scale_action=now,
        )

        assert metrics.total_agents == 10
        assert metrics.active_agents == 5
        assert metrics.idle_agents == 3
        assert metrics.busy_agents == 2
        assert metrics.total_capacity == 50
        assert metrics.current_utilization == 65.5
        assert metrics.scaling_events == 15
        assert metrics.last_scale_action == now

    def test_pool_metrics_to_dict(self):
        """Test PoolMetrics conversion to dict"""
        metrics = PoolMetrics(total_agents=3, current_utilization=40.0)
        metrics_dict = asdict(metrics)

        assert metrics_dict["total_agents"] == 3
        assert metrics_dict["current_utilization"] == 40.0


class TestAgentPoolInitialization:
    """Test AgentPool initialization and configuration"""

    @pytest.fixture
    def mock_agent_manager(self):
        """Create a mock AgentManager with mock AgentFactory"""
        manager = MagicMock()
        factory = MagicMock()
        factory.active_agents = {}
        manager.agent_factory = factory
        return manager

    def test_agent_pool_initialization(self, mock_agent_manager):
        """Test AgentPool basic initialization"""
        pool = AgentPool(mock_agent_manager)

        assert pool.agent_manager == mock_agent_manager
        assert pool.agent_factory == mock_agent_manager.agent_factory
        assert pool.running is False
        assert pool.pool_management_task is None
        assert isinstance(pool.pool_config, PoolConfiguration)
        assert isinstance(pool.pool_metrics, PoolMetrics)

    def test_default_config_creation(self, mock_agent_manager):
        """Test default configuration is created correctly"""
        pool = AgentPool(mock_agent_manager)
        config = pool.pool_config

        # Verify min agents per type
        assert AgentType.SYSTEM_MONITOR in config.min_agents_per_type
        assert config.min_agents_per_type[AgentType.SYSTEM_MONITOR] == 1

        # Verify max agents per type
        assert AgentType.DATA_ANALYSIS in config.max_agents_per_type
        assert config.max_agents_per_type[AgentType.DATA_ANALYSIS] == 5

        # Verify thresholds
        assert config.scale_up_threshold == 75.0
        assert config.scale_down_threshold == 25.0
        assert config.scale_check_interval == 60
        assert config.idle_timeout == 300

    def test_configure_pool(self, mock_agent_manager):
        """Test pool configuration update"""
        pool = AgentPool(mock_agent_manager)

        new_config = PoolConfiguration(
            min_agents_per_type={AgentType.CODE_EXECUTION: 2},
            max_agents_per_type={AgentType.CODE_EXECUTION: 8},
            scale_up_threshold=90.0,
            scale_down_threshold=10.0,
            scale_check_interval=120,
            idle_timeout=600,
        )

        pool.configure_pool(new_config)

        assert pool.pool_config == new_config
        assert pool.pool_config.scale_up_threshold == 90.0


class TestAgentPoolLifecycle:
    """Test AgentPool start/stop lifecycle"""

    @pytest.fixture
    def mock_agent_manager(self):
        """Create a mock AgentManager"""
        manager = MagicMock()
        factory = MagicMock()
        factory.active_agents = {}
        factory.create_agent = AsyncMock(return_value="agent_001")
        manager.agent_factory = factory
        return manager

    @pytest.mark.asyncio
    async def test_start_pool(self, mock_agent_manager):
        """Test starting the agent pool"""
        pool = AgentPool(mock_agent_manager)

        # Start pool in background
        start_task = asyncio.create_task(pool.start_pool())
        await asyncio.sleep(0.1)  # Let it initialize

        assert pool.running is True
        assert pool.pool_management_task is not None

        # Clean up
        await pool.stop_pool()
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_pool_already_running(self, mock_agent_manager):
        """Test starting pool when already running"""
        pool = AgentPool(mock_agent_manager)
        pool.running = True

        await pool.start_pool()

        # Should return early without creating management task
        assert pool.pool_management_task is None

    @pytest.mark.asyncio
    async def test_stop_pool(self, mock_agent_manager):
        """Test stopping the agent pool"""
        pool = AgentPool(mock_agent_manager)
        pool.running = True
        pool.pool_management_task = MagicMock()
        pool.pool_management_task.cancel = MagicMock()

        await pool.stop_pool()

        assert pool.running is False
        pool.pool_management_task.cancel.assert_called_once()


class TestAgentPoolMinimumAgents:
    """Test ensuring minimum agents"""

    @pytest.fixture
    def mock_agent_manager(self):
        """Create a mock AgentManager"""
        manager = MagicMock()
        factory = MagicMock()
        factory.active_agents = {}
        factory.create_agent = AsyncMock(return_value="new_agent_id")
        manager.agent_factory = factory
        return manager

    @pytest.mark.asyncio
    async def test_ensure_minimum_agents_creates_agents(self, mock_agent_manager):
        """Test that minimum agents are created when below threshold"""
        pool = AgentPool(mock_agent_manager)

        # Configure minimum of 2 SYSTEM_MONITOR agents
        pool.pool_config.min_agents_per_type = {AgentType.SYSTEM_MONITOR: 2}

        await pool._ensure_minimum_agents()

        # Should have called create_agent twice
        assert mock_agent_manager.agent_factory.create_agent.call_count == 2

    @pytest.mark.asyncio
    async def test_ensure_minimum_agents_already_met(self, mock_agent_manager):
        """Test no agents created when minimum already met"""
        pool = AgentPool(mock_agent_manager)

        # Create mock agents that are already present
        mock_agent = MagicMock()
        mock_agent.config.agent_type = AgentType.SYSTEM_MONITOR
        mock_agent_manager.agent_factory.active_agents = {
            "agent_1": mock_agent,
            "agent_2": mock_agent,
        }

        pool.pool_config.min_agents_per_type = {AgentType.SYSTEM_MONITOR: 2}

        await pool._ensure_minimum_agents()

        # Should not have called create_agent
        mock_agent_manager.agent_factory.create_agent.assert_not_called()


class TestAgentPoolCountAgents:
    """Test counting agents by type"""

    @pytest.fixture
    def mock_agent_manager_with_agents(self):
        """Create a mock AgentManager with agents"""
        manager = MagicMock()
        factory = MagicMock()

        # Create mock agents of different types
        agent1 = MagicMock()
        agent1.config.agent_type = AgentType.SYSTEM_MONITOR

        agent2 = MagicMock()
        agent2.config.agent_type = AgentType.DATA_ANALYSIS

        agent3 = MagicMock()
        agent3.config.agent_type = AgentType.SYSTEM_MONITOR

        factory.active_agents = {
            "agent_1": agent1,
            "agent_2": agent2,
            "agent_3": agent3,
        }
        manager.agent_factory = factory
        return manager

    @pytest.mark.asyncio
    async def test_count_agents_of_type(self, mock_agent_manager_with_agents):
        """Test counting agents by type"""
        pool = AgentPool(mock_agent_manager_with_agents)

        # Count SYSTEM_MONITOR agents
        count = await pool._count_agents_of_type(AgentType.SYSTEM_MONITOR)
        assert count == 2

        # Count DATA_ANALYSIS agents
        count = await pool._count_agents_of_type(AgentType.DATA_ANALYSIS)
        assert count == 1

        # Count CODE_EXECUTION agents (should be 0)
        count = await pool._count_agents_of_type(AgentType.CODE_EXECUTION)
        assert count == 0


class TestAgentPoolRequestAgent:
    """Test agent request and allocation"""

    @pytest.fixture
    def mock_agent_manager(self):
        """Create a mock AgentManager with agents"""
        manager = MagicMock()
        factory = MagicMock()

        # Mock agent
        mock_agent = MagicMock()
        mock_agent.config.agent_type = AgentType.DATA_ANALYSIS
        mock_agent.config.max_concurrent_tasks = 5
        mock_agent.current_tasks = {}

        factory.active_agents = {"agent_1": mock_agent}
        factory.find_capable_agents = AsyncMock(return_value=["agent_1"])
        factory.get_agent = AsyncMock(return_value=mock_agent)
        factory.create_agent = AsyncMock(return_value="new_agent_id")

        manager.agent_factory = factory
        return manager

    @pytest.mark.asyncio
    async def test_request_agent_finds_suitable_agent(self, mock_agent_manager):
        """Test requesting agent with matching capabilities"""
        pool = AgentPool(mock_agent_manager)

        result = await pool.request_agent(["statistical_analysis"])

        assert result == "agent_1"
        mock_agent_manager.agent_factory.find_capable_agents.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_agent_creates_on_demand(self, mock_agent_manager):
        """Test creating agent on demand when none suitable"""
        pool = AgentPool(mock_agent_manager)
        mock_agent_manager.agent_factory.find_capable_agents = AsyncMock(return_value=[])

        result = await pool.request_agent(["data_analysis"])

        assert result == "new_agent_id"

    @pytest.mark.asyncio
    async def test_request_agent_handles_exception(self, mock_agent_manager):
        """Test exception handling during agent request"""
        pool = AgentPool(mock_agent_manager)
        mock_agent_manager.agent_factory.find_capable_agents = AsyncMock(
            side_effect=Exception("Test error")
        )

        result = await pool.request_agent(["some_capability"])

        assert result is None


class TestAgentPoolOptimalSelection:
    """Test optimal agent selection logic"""

    @pytest.fixture
    def pool_with_agents(self):
        """Create pool with multiple agents"""
        manager = MagicMock()
        factory = MagicMock()

        # Agent with low load
        agent1 = MagicMock()
        agent1.config.max_concurrent_tasks = 10
        agent1.current_tasks = {"task1": {}}  # 1/10 = 10% load

        # Agent with high load
        agent2 = MagicMock()
        agent2.config.max_concurrent_tasks = 10
        agent2.current_tasks = {f"task{i}": {} for i in range(8)}  # 8/10 = 80% load

        factory.active_agents = {"low_load": agent1, "high_load": agent2}
        factory.get_agent = AsyncMock(
            side_effect=lambda id: {"low_load": agent1, "high_load": agent2}.get(id)
        )

        manager.agent_factory = factory

        pool = AgentPool(manager)
        return pool

    @pytest.mark.asyncio
    async def test_select_optimal_agent_prefers_low_load(self, pool_with_agents):
        """Test that lower load agents are preferred"""
        result = await pool_with_agents._select_optimal_agent(["low_load", "high_load"])

        # Low load agent should be selected due to lower load factor
        assert result == "low_load"

    @pytest.mark.asyncio
    async def test_select_optimal_agent_fallback(self, pool_with_agents):
        """Test fallback to first agent if none found"""
        pool_with_agents.agent_factory.get_agent = AsyncMock(return_value=None)

        result = await pool_with_agents._select_optimal_agent(["agent_1", "agent_2"])

        assert result == "agent_1"

    def test_get_agent_performance_score_no_history(self, pool_with_agents):
        """Test performance score with no history"""
        score = pool_with_agents._get_agent_performance_score("new_agent")
        assert score == 0.5  # Default score

    def test_get_agent_performance_score_with_history(self, pool_with_agents):
        """Test performance score with usage history"""
        pool_with_agents.agent_usage_history["agent_1"] = [0.2, 0.3, 0.25, 0.2, 0.3]
        score = pool_with_agents._get_agent_performance_score("agent_1")

        # Score should be inverse of average usage (1.0 - 0.25 = 0.75)
        assert 0.7 < score < 0.8


class TestAgentPoolCapabilityMapping:
    """Test capability to agent type mapping"""

    @pytest.fixture
    def pool(self):
        """Create basic pool"""
        manager = MagicMock()
        manager.agent_factory = MagicMock()
        manager.agent_factory.active_agents = {}
        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_determine_agent_type_data_analysis(self, pool):
        """Test mapping data analysis capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["data_analysis"])
        assert result == AgentType.DATA_ANALYSIS

        result = await pool._determine_agent_type_for_capabilities(["statistical_analysis"])
        assert result == AgentType.DATA_ANALYSIS

    @pytest.mark.asyncio
    async def test_determine_agent_type_system_monitor(self, pool):
        """Test mapping system monitor capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["system_monitoring"])
        assert result == AgentType.SYSTEM_MONITOR

        result = await pool._determine_agent_type_for_capabilities(["health_checks"])
        assert result == AgentType.SYSTEM_MONITOR

    @pytest.mark.asyncio
    async def test_determine_agent_type_code_execution(self, pool):
        """Test mapping code execution capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["code_execution"])
        assert result == AgentType.CODE_EXECUTION

        result = await pool._determine_agent_type_for_capabilities(["python_execution"])
        assert result == AgentType.CODE_EXECUTION

    @pytest.mark.asyncio
    async def test_determine_agent_type_knowledge_retrieval(self, pool):
        """Test mapping knowledge retrieval capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["knowledge_search"])
        assert result == AgentType.KNOWLEDGE_RETRIEVAL

        result = await pool._determine_agent_type_for_capabilities(["document_retrieval"])
        assert result == AgentType.KNOWLEDGE_RETRIEVAL

    @pytest.mark.asyncio
    async def test_determine_agent_type_reporting(self, pool):
        """Test mapping reporting capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["report_generation"])
        assert result == AgentType.REPORTING

    @pytest.mark.asyncio
    async def test_determine_agent_type_performance(self, pool):
        """Test mapping performance analysis capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["performance_analysis"])
        assert result == AgentType.PERFORMANCE_ANALYSIS

        result = await pool._determine_agent_type_for_capabilities(["benchmarking"])
        assert result == AgentType.PERFORMANCE_ANALYSIS

    @pytest.mark.asyncio
    async def test_determine_agent_type_unknown_fallback(self, pool):
        """Test fallback for unknown capabilities"""
        result = await pool._determine_agent_type_for_capabilities(["unknown_capability"])
        assert result == AgentType.DATA_ANALYSIS  # Default fallback


class TestAgentPoolMetricsUpdate:
    """Test pool metrics update"""

    @pytest.fixture
    def pool_with_mixed_agents(self):
        """Create pool with agents in various states"""
        manager = MagicMock()
        factory = MagicMock()

        # Idle agent
        idle_agent = MagicMock()
        idle_agent.config.max_concurrent_tasks = 5
        idle_agent.current_tasks = {}

        # Busy agent (at max capacity)
        busy_agent = MagicMock()
        busy_agent.config.max_concurrent_tasks = 3
        busy_agent.current_tasks = {"t1": {}, "t2": {}, "t3": {}}

        # Active agent (some tasks)
        active_agent = MagicMock()
        active_agent.config.max_concurrent_tasks = 5
        active_agent.current_tasks = {"t1": {}, "t2": {}}

        factory.active_agents = {
            "idle": idle_agent,
            "busy": busy_agent,
            "active": active_agent,
        }
        manager.agent_factory = factory

        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_update_pool_metrics(self, pool_with_mixed_agents):
        """Test pool metrics are calculated correctly"""
        await pool_with_mixed_agents._update_pool_metrics()

        metrics = pool_with_mixed_agents.pool_metrics

        assert metrics.total_agents == 3
        assert metrics.idle_agents == 1
        assert metrics.busy_agents == 2  # busy + active have tasks
        assert metrics.total_capacity == 13  # 5 + 3 + 5
        # Utilization: (0 + 3 + 2) / 13 * 100 = ~38.5%
        assert 38 < metrics.current_utilization < 39


class TestAgentPoolScaling:
    """Test scaling up and down"""

    @pytest.fixture
    def pool_for_scaling(self):
        """Create pool configured for scaling tests"""
        manager = MagicMock()
        factory = MagicMock()

        agent = MagicMock()
        agent.config.agent_type = AgentType.DATA_ANALYSIS
        agent.config.max_concurrent_tasks = 10
        agent.current_tasks = {f"task{i}": {} for i in range(8)}  # 80% load
        agent.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)

        factory.active_agents = {"agent_1": agent}
        factory.create_agent = AsyncMock(return_value="new_agent")
        factory.shutdown_agent = AsyncMock(return_value=True)

        manager.agent_factory = factory

        pool = AgentPool(manager)
        pool.pool_config.scale_up_threshold = 75.0
        pool.pool_config.scale_down_threshold = 25.0
        pool.pool_metrics.current_utilization = 80.0

        return pool

    @pytest.mark.asyncio
    async def test_check_scaling_needs_scale_up(self, pool_for_scaling):
        """Test scaling up when utilization is high"""
        pool_for_scaling.pool_metrics.current_utilization = 80.0  # Above 75%

        with patch.object(pool_for_scaling, "_scale_up", new_callable=AsyncMock) as mock_scale_up:
            await pool_for_scaling._check_scaling_needs()
            mock_scale_up.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_scaling_needs_scale_down(self, pool_for_scaling):
        """Test scaling down when utilization is low"""
        pool_for_scaling.pool_metrics.current_utilization = 10.0  # Below 25%

        with patch.object(
            pool_for_scaling, "_scale_down", new_callable=AsyncMock
        ) as mock_scale_down:
            await pool_for_scaling._check_scaling_needs()
            mock_scale_down.assert_called_once()

    @pytest.mark.asyncio
    async def test_scale_up_creates_agent(self, pool_for_scaling):
        """Test that scale up creates new agent"""
        pool_for_scaling.pool_config.max_agents_per_type = {AgentType.DATA_ANALYSIS: 10}

        await pool_for_scaling._scale_up()

        pool_for_scaling.agent_factory.create_agent.assert_called()

    @pytest.mark.asyncio
    async def test_analyze_demand_by_type(self, pool_for_scaling):
        """Test demand analysis calculation"""
        result = await pool_for_scaling._analyze_demand_by_type()

        assert AgentType.DATA_ANALYSIS in result
        assert result[AgentType.DATA_ANALYSIS] == 0.8  # 8/10 tasks


class TestAgentPoolScaleDown:
    """Test scale down behavior"""

    @pytest.fixture
    def pool_for_scale_down(self):
        """Create pool with idle agents for scale down"""
        manager = MagicMock()
        factory = MagicMock()

        idle_agent = MagicMock()
        idle_agent.config.agent_type = AgentType.DATA_ANALYSIS
        idle_agent.config.max_concurrent_tasks = 5
        idle_agent.current_tasks = {}  # No tasks = idle
        idle_agent.last_activity = datetime.now(timezone.utc) - timedelta(minutes=10)  # Idle for 10 mins

        factory.active_agents = {"idle_agent": idle_agent}
        factory.shutdown_agent = AsyncMock(return_value=True)

        manager.agent_factory = factory

        pool = AgentPool(manager)
        pool.pool_config.min_agents_per_type = {AgentType.DATA_ANALYSIS: 0}
        pool.pool_config.idle_timeout = 300  # 5 minutes

        return pool

    @pytest.mark.asyncio
    async def test_scale_down_removes_idle_agent(self, pool_for_scale_down):
        """Test that scale down removes idle agents"""
        await pool_for_scale_down._scale_down()

        pool_for_scale_down.agent_factory.shutdown_agent.assert_called_once_with("idle_agent")

    @pytest.mark.asyncio
    async def test_scale_down_respects_minimum(self, pool_for_scale_down):
        """Test that scale down respects minimum agent count"""
        pool_for_scale_down.pool_config.min_agents_per_type = {AgentType.DATA_ANALYSIS: 1}

        await pool_for_scale_down._scale_down()

        pool_for_scale_down.agent_factory.shutdown_agent.assert_not_called()


class TestAgentPoolUsageHistory:
    """Test agent usage history tracking"""

    @pytest.fixture
    def pool_with_agents(self):
        """Create pool with agents for tracking"""
        manager = MagicMock()
        factory = MagicMock()

        agent = MagicMock()
        agent.config.max_concurrent_tasks = 10
        agent.current_tasks = {"t1": {}, "t2": {}, "t3": {}}  # 30% utilization

        factory.active_agents = {"agent_1": agent}
        manager.agent_factory = factory

        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_update_agent_usage_history(self, pool_with_agents):
        """Test usage history is recorded"""
        await pool_with_agents._update_agent_usage_history()

        assert "agent_1" in pool_with_agents.agent_usage_history
        assert len(pool_with_agents.agent_usage_history["agent_1"]) == 1
        assert pool_with_agents.agent_usage_history["agent_1"][0] == 0.3

    @pytest.mark.asyncio
    async def test_usage_history_trimmed_at_100(self, pool_with_agents):
        """Test usage history is trimmed to 100 entries"""
        # Pre-fill with 100 entries
        pool_with_agents.agent_usage_history["agent_1"] = [0.5] * 100

        await pool_with_agents._update_agent_usage_history()

        # Should still be 100 (trimmed after adding new one)
        assert len(pool_with_agents.agent_usage_history["agent_1"]) == 100


class TestAgentPoolRecordScalingEvent:
    """Test scaling event recording"""

    @pytest.fixture
    def pool(self):
        """Create basic pool"""
        manager = MagicMock()
        manager.agent_factory = MagicMock()
        manager.agent_factory.active_agents = {}
        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_record_scaling_event(self, pool):
        """Test scaling event is recorded correctly"""
        pool.pool_metrics.current_utilization = 85.0
        pool.pool_metrics.total_agents = 5

        await pool._record_scaling_event("scale_up", AgentType.DATA_ANALYSIS, "demand_based")

        assert len(pool.scaling_history) == 1
        event = pool.scaling_history[0]
        assert event["action"] == "scale_up"
        assert event["agent_type"] == AgentType.DATA_ANALYSIS.value  # Use enum value
        assert event["reason"] == "demand_based"
        assert event["pool_utilization"] == 85.0
        assert event["total_agents_before"] == 5

    @pytest.mark.asyncio
    async def test_record_scaling_event_updates_metrics(self, pool):
        """Test scaling event updates metrics"""
        await pool._record_scaling_event("scale_down", AgentType.SYSTEM_MONITOR, "idle_cleanup")

        assert pool.pool_metrics.scaling_events == 1
        assert pool.pool_metrics.last_scale_action is not None


class TestAgentPoolStatus:
    """Test pool status reporting"""

    @pytest.fixture
    def pool_with_data(self):
        """Create pool with test data"""
        manager = MagicMock()
        factory = MagicMock()

        agent = MagicMock()
        agent.config.agent_type = AgentType.DATA_ANALYSIS
        agent.config.max_concurrent_tasks = 10
        agent.current_tasks = {"t1": {}}

        factory.active_agents = {"agent_1": agent}
        manager.agent_factory = factory

        pool = AgentPool(manager)
        pool.pool_metrics = PoolMetrics(
            total_agents=1,
            active_agents=1,
            idle_agents=0,
            busy_agents=0,
            total_capacity=10,
            current_utilization=10.0,
            scaling_events=2,
            last_scale_action=datetime.now(timezone.utc),
        )

        # Add scaling history
        pool.scaling_history = [
            {
                "timestamp": datetime.now(timezone.utc),
                "action": "scale_up",
                "agent_type": "DATA_ANALYSIS",
                "reason": "demand",
            }
        ]

        return pool

    def test_get_pool_status(self, pool_with_data):
        """Test comprehensive pool status"""
        status = pool_with_data.get_pool_status()

        assert status["pool_running"] is False
        assert "metrics" in status
        assert status["metrics"]["total_agents"] == 1
        assert status["metrics"]["current_utilization"] == 10.0
        assert "agent_type_breakdown" in status
        assert "configuration" in status
        assert "recent_scaling_events" in status
        assert len(status["recent_scaling_events"]) == 1


class TestAgentPoolAnalytics:
    """Test pool analytics"""

    @pytest.fixture
    def pool_with_history(self):
        """Create pool with usage history"""
        manager = MagicMock()
        manager.agent_factory = MagicMock()
        manager.agent_factory.active_agents = {}

        pool = AgentPool(manager)
        pool.agent_usage_history = {
            "agent_1": [0.1, 0.2, 0.3, 0.4, 0.5],
            "agent_2": [0.8, 0.9, 0.85, 0.95, 0.88],
        }
        pool.scaling_history = [
            {"timestamp": datetime.now(timezone.utc) - timedelta(minutes=10), "action": "scale_up"},
            {
                "timestamp": datetime.now(timezone.utc) - timedelta(minutes=5),
                "action": "scale_down",
            },
            {"timestamp": datetime.now(timezone.utc), "action": "scale_up"},
        ]
        pool.pool_metrics.current_utilization = 50.0

        return pool

    @pytest.mark.asyncio
    async def test_get_pool_analytics(self, pool_with_history):
        """Test analytics generation"""
        analytics = await pool_with_history.get_pool_analytics()

        assert "usage_patterns" in analytics
        assert "agent_1" in analytics["usage_patterns"]
        assert analytics["usage_patterns"]["agent_1"]["average_utilization"] == 0.3
        assert analytics["usage_patterns"]["agent_1"]["peak_utilization"] == 0.5

        assert "scaling_efficiency" in analytics
        assert analytics["scaling_efficiency"]["total_scale_events"] == 3
        assert analytics["scaling_efficiency"]["scale_up_events"] == 2
        assert analytics["scaling_efficiency"]["scale_down_events"] == 1

        assert analytics["pool_health"] == "optimal"  # 50% is in range

    @pytest.mark.asyncio
    async def test_pool_health_suboptimal(self, pool_with_history):
        """Test pool health when suboptimal"""
        pool_with_history.pool_metrics.current_utilization = 95.0

        analytics = await pool_with_history.get_pool_analytics()

        assert analytics["pool_health"] == "suboptimal"


class TestAgentPoolRecommendations:
    """Test pool recommendations generation"""

    @pytest.fixture
    def pool(self):
        """Create basic pool"""
        manager = MagicMock()
        manager.agent_factory = MagicMock()
        manager.agent_factory.active_agents = {}
        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_recommendations_high_utilization(self, pool):
        """Test recommendations for high utilization"""
        pool.pool_metrics.current_utilization = 95.0

        recommendations = await pool._generate_pool_recommendations()

        assert "Consider increasing maximum agents per type" in recommendations

    @pytest.mark.asyncio
    async def test_recommendations_low_utilization(self, pool):
        """Test recommendations for low utilization"""
        pool.pool_metrics.current_utilization = 5.0

        recommendations = await pool._generate_pool_recommendations()

        assert "Consider reducing minimum agents per type" in recommendations

    @pytest.mark.asyncio
    async def test_recommendations_many_idle(self, pool):
        """Test recommendations when many agents idle"""
        pool.pool_metrics.idle_agents = 10
        pool.pool_metrics.busy_agents = 2

        recommendations = await pool._generate_pool_recommendations()

        assert "Many agents are idle - consider adjusting scale-down threshold" in recommendations

    @pytest.mark.asyncio
    async def test_recommendations_frequent_scaling(self, pool):
        """Test recommendations for frequent scaling"""
        pool.scaling_history = [{"action": "scale"} for _ in range(25)]

        recommendations = await pool._generate_pool_recommendations()

        assert "Frequent scaling detected - consider adjusting thresholds" in recommendations


class TestGlobalAgentPoolFunctions:
    """Test global helper functions"""

    def test_get_agent_pool_returns_none_initially(self):
        """Test get_agent_pool returns None when not created"""
        import src.core.subagents.agent_pool as module

        module._agent_pool = None

        result = get_agent_pool()

        assert result is None

    @patch("src.core.subagents.agent_manager.create_agent_manager")
    def test_create_agent_pool(self, mock_create_manager):
        """Test create_agent_pool creates singleton"""
        import src.core.subagents.agent_pool as module

        module._agent_pool = None

        mock_manager = MagicMock()
        mock_manager.agent_factory = MagicMock()
        mock_manager.agent_factory.active_agents = {}
        mock_create_manager.return_value = mock_manager

        pool = create_agent_pool()

        assert pool is not None
        assert isinstance(pool, AgentPool)

    @patch("src.core.subagents.agent_manager.create_agent_manager")
    def test_create_agent_pool_returns_existing(self, mock_create_manager):
        """Test create_agent_pool returns existing instance"""
        import src.core.subagents.agent_pool as module

        mock_manager = MagicMock()
        mock_manager.agent_factory = MagicMock()
        mock_manager.agent_factory.active_agents = {}
        mock_create_manager.return_value = mock_manager

        pool1 = create_agent_pool()
        pool2 = create_agent_pool()

        assert pool1 is pool2


class TestPoolManagementLoop:
    """Test the pool management loop"""

    @pytest.fixture
    def pool(self):
        """Create pool for loop testing"""
        manager = MagicMock()
        factory = MagicMock()
        factory.active_agents = {}
        manager.agent_factory = factory

        pool = AgentPool(manager)
        pool.pool_config.scale_check_interval = 0.1  # Fast for testing
        return pool

    @pytest.mark.asyncio
    async def test_pool_management_loop_runs(self, pool):
        """Test that pool management loop executes"""
        pool.running = True
        call_count = 0

        async def mock_update():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                pool.running = False

        pool._update_pool_metrics = mock_update
        pool._check_scaling_needs = AsyncMock()
        pool._update_agent_usage_history = AsyncMock()
        pool._cleanup_idle_agents = AsyncMock()
        pool._record_pool_state = AsyncMock()

        await pool._pool_management_loop()

        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_pool_management_loop_handles_exception(self, pool):
        """Test that loop continues after exception"""
        pool.running = True
        call_count = 0

        async def mock_update():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Test error")
            if call_count >= 2:
                pool.running = False

        pool._update_pool_metrics = mock_update
        pool._check_scaling_needs = AsyncMock()
        pool._update_agent_usage_history = AsyncMock()
        pool._cleanup_idle_agents = AsyncMock()
        pool._record_pool_state = AsyncMock()

        await pool._pool_management_loop()

        # Loop should have continued after error
        assert call_count >= 2


class TestCleanupIdleAgents:
    """Test cleanup idle agents method"""

    @pytest.fixture
    def pool(self):
        """Create basic pool"""
        manager = MagicMock()
        manager.agent_factory = MagicMock()
        manager.agent_factory.active_agents = {}
        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_cleanup_idle_agents(self, pool):
        """Test cleanup method exists and runs"""
        # This is a placeholder method that delegates to _scale_down
        await pool._cleanup_idle_agents()
        # No assertion needed - just verify it doesn't raise


class TestRecordPoolState:
    """Test pool state recording"""

    @pytest.fixture
    def pool(self):
        """Create pool for state recording"""
        manager = MagicMock()
        factory = MagicMock()
        factory.active_agents = {}
        manager.agent_factory = factory
        return AgentPool(manager)

    @pytest.mark.asyncio
    async def test_record_pool_state(self, pool):
        """Test pool state is recorded"""
        await pool._record_pool_state()

        # State should be recorded but scaling_history holds scaling events
        # Pool state recording doesn't add to scaling_history
        # This test just verifies no errors occur

    @pytest.mark.asyncio
    async def test_record_pool_state_trims_history(self, pool):
        """Test pool state history is trimmed"""
        # Pre-fill with many entries
        pool.scaling_history = [{"test": i} for i in range(1500)]

        await pool._record_pool_state()

        # Should be trimmed to 1440
        assert len(pool.scaling_history) == 1440
