"""Integration tests for AgentHealthMonitorAgent + AgentRouterAgent integration.

Tests ADR-023 compliance: Health-aware routing with unhealthy agent filtering.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.als.health_monitor import AgentHealthMonitorAgent, HealthStatus
from src.core.als.router import (
    AgentRouterAgent,
    AgentUnhealthyError,
    RouterService,
)
from src.core.shared.interfaces import TaskData


def _async_mock(return_value):
    """Create an async mock that returns the given value."""

    async def _async_return(*args, **kwargs):
        return return_value

    return _async_return


@pytest.fixture
def mock_task():
    """Create a mock task for testing."""
    return TaskData(
        id="task-001",
        title="Test Task",
        description="Test description",
    )


@pytest.fixture
def mock_agent_healthy():
    """Mock healthy agent registration."""
    agent = MagicMock()
    agent.agent_id = "healthy-agent"
    agent.tenant_id = None
    return agent


@pytest.fixture
def mock_agent_unhealthy():
    """Mock unhealthy agent registration."""
    agent = MagicMock()
    agent.agent_id = "unhealthy-agent"
    agent.tenant_id = None
    return agent


@pytest.fixture
def mock_health_monitor():
    """Mock health monitor that tracks agent availability."""
    monitor = MagicMock(spec=AgentHealthMonitorAgent)
    # Default: all agents available
    monitor.is_agent_available.return_value = True
    return monitor


@pytest.fixture
def mock_health_monitor_with_disabled():
    """Mock health monitor with specific disabled agents."""
    monitor = MagicMock(spec=AgentHealthMonitorAgent)
    disabled_agents = {"unhealthy-agent", "another-unhealthy"}

    def _is_available(agent_id):
        return agent_id not in disabled_agents

    monitor.is_agent_available = _is_available
    return monitor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_filters_disabled_agents(
    mock_agent_healthy, mock_agent_unhealthy, mock_health_monitor_with_disabled
):
    """Test that RouterService filters out disabled agents."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        health_monitor=mock_health_monitor_with_disabled,
    )

    agents = [mock_agent_healthy, mock_agent_unhealthy]
    healthy_agents = service._filter_healthy_agents(agents, "test_dept")

    assert len(healthy_agents) == 1
    assert healthy_agents[0].agent_id == "healthy-agent"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_no_health_monitor(mock_agent_healthy, mock_agent_unhealthy):
    """Test that routing proceeds normally when no health monitor configured."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        health_monitor=None,
    )

    agents = [mock_agent_healthy, mock_agent_unhealthy]
    healthy_agents = service._filter_healthy_agents(agents, "test_dept")

    # All agents pass through when no health monitor
    assert len(healthy_agents) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_all_agents_unhealthy():
    """Test behavior when all agents are unhealthy."""
    # Create a monitor where ALL agents are disabled
    monitor = MagicMock(spec=AgentHealthMonitorAgent)

    def _all_disabled(agent_id):
        return False  # All agents disabled

    monitor.is_agent_available = _all_disabled

    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        health_monitor=monitor,
    )

    # Create all unhealthy agents
    unhealthy1 = MagicMock()
    unhealthy1.agent_id = "unhealthy-agent-1"
    unhealthy2 = MagicMock()
    unhealthy2.agent_id = "unhealthy-agent-2"

    agents = [unhealthy1, unhealthy2]
    healthy_agents = service._filter_healthy_agents(agents, "test_dept")

    assert len(healthy_agents) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_unhealthy_error_attributes():
    """Test AgentUnhealthyError has correct attributes."""
    error = AgentUnhealthyError(
        tenant_id=42,
        task_id="task-123",
        department="finance",
        unhealthy_agents=["agent-1", "agent-2"],
    )

    assert error.tenant_id == 42
    assert error.task_id == "task-123"
    assert error.department == "finance"
    assert error.unhealthy_agents == ["agent-1", "agent-2"]
    assert "task-123" in str(error)
    assert "finance" in str(error)
    assert "agent-1" in str(error)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_router_agent_process_task_unhealthy_agent(mock_task):
    """Test AgentRouterAgent handles unhealthy agent errors correctly."""
    signal_bus = MagicMock()

    # Create a health monitor that marks all agents as unhealthy
    health_monitor = MagicMock()
    health_monitor.is_agent_available.return_value = False

    agent = AgentRouterAgent(
        tenant_id=1,
        signal_bus=signal_bus,
        health_monitor=health_monitor,
    )

    # Mock the service to avoid initialization
    agent._service._redis = MagicMock()
    agent._service._registry = MagicMock()
    agent._service._llm = MagicMock()

    # Create mock agents for registry
    mock_agent = MagicMock()
    mock_agent.agent_id = "unhealthy-agent"
    mock_agent.tenant_id = None

    # Mock registry to return our unhealthy agent
    agent._service._registry.list_agents.return_value = [mock_agent]

    # Mock deterministic router to return a valid department
    from src.core.als.enterprise.departments.deterministic_router import Department

    with patch("src.core.als.router.DeterministicRouter") as mock_deterministic:
        mock_deterministic.return_value.route.return_value = Department.FINANCE

        result = await agent.process_task(mock_task)

    # After health filtering, no healthy agents remain
    # Routing fails because no agents available after filtering
    assert result.success is False
    # Should indicate no agents found (either "No healthy agents" or "No agent found")
    assert "No" in result.error_message and ("healthy" in result.error_message.lower() or "agent found" in result.error_message)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_health_monitor_integration_with_real_monitor(mock_task):
    """Test integration with real AgentHealthMonitorAgent."""
    # Create real health monitor
    health_monitor = AgentHealthMonitorAgent(tenant_id=1)

    # Record some failures for an agent to make it unhealthy
    for _ in range(3):
        health_monitor.record_task_result(
            agent_id="failing-agent",
            success=False,
            latency_ms=100.0,
            error_type="TestError",
        )

    # Check alerts to trigger the disable logic
    alerts = health_monitor.check_agent_alerts("failing-agent")

    # Record successes for another agent
    for _ in range(5):
        health_monitor.record_task_result(
            agent_id="healthy-agent",
            success=True,
            latency_ms=50.0,
        )

    # Check availability
    assert health_monitor.is_agent_available("healthy-agent") is True
    # The failing agent should be disabled after 3 consecutive failures + alert check
    assert health_monitor.is_agent_available("failing-agent") is False
    # Should have generated an alert
    assert len(alerts) >= 1
    assert any(a.alert_type == "agent_disabled" for a in alerts)


@pytest.mark.unit
def test_agent_router_agent_accepts_health_monitor_parameter():
    """Test that AgentRouterAgent accepts health_monitor parameter."""
    signal_bus = MagicMock()
    health_monitor = MagicMock()

    agent = AgentRouterAgent(
        tenant_id=1,
        signal_bus=signal_bus,
        health_monitor=health_monitor,
    )

    assert agent._health_monitor is health_monitor
    assert agent._service._health_monitor is health_monitor


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_logs_filtered_agents(mock_health_monitor_with_disabled):
    """Test that filtered unhealthy agents are logged."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        health_monitor=mock_health_monitor_with_disabled,
    )

    healthy = MagicMock()
    healthy.agent_id = "healthy-agent"

    unhealthy = MagicMock()
    unhealthy.agent_id = "unhealthy-agent"

    agents = [healthy, unhealthy]

    # Should log warning about filtered agents
    with patch("src.core.als.router.logger") as mock_logger:
        healthy_agents = service._filter_healthy_agents(agents, "finance")

        assert len(healthy_agents) == 1
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert "Filtered" in call_args[0][0]
        assert "unhealthy-agent" in str(call_args)
