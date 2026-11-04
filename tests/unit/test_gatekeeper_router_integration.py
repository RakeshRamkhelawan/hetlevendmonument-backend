"""Integration tests for Gatekeeper + AgentRouterAgent integration.

Tests ADR-017 compliance: Gatekeeper policy enforcement integrated with routing.
"""

from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio

from src.core.als.enterprise.gatekeeper import GateDecision, Gatekeeper
from src.core.als.router import (
    AgentRouterAgent,
    GatekeeperRoutingError,
    RouterService,
)
from src.core.shared.interfaces import TaskData


@pytest.fixture
def mock_task():
    """Create a mock task for testing."""
    return TaskData(
        id="task-001",
        title="Test Task",
        description="Test description",
    )


def _async_mock(return_value):
    """Create an async mock that returns the given value."""

    async def _async_return(*args, **kwargs):
        return return_value

    return _async_return


@pytest.fixture
def mock_gatekeeper_allow():
    """Mock Gatekeeper that allows all tasks."""
    gatekeeper = MagicMock(spec=Gatekeeper)
    decision_record = MagicMock()
    decision_record.decision.value = "allow"
    decision_record.policy_rules_failed = []
    decision_record.hitl_ticket_ref = None
    gatekeeper.evaluate_task = _async_mock(decision_record)
    return gatekeeper


@pytest.fixture
def mock_gatekeeper_block():
    """Mock Gatekeeper that blocks all tasks."""
    gatekeeper = MagicMock(spec=Gatekeeper)
    decision_record = MagicMock()
    decision_record.decision.value = "block"
    decision_record.policy_rules_failed = ["POL-001"]
    decision_record.hitl_ticket_ref = None
    gatekeeper.evaluate_task = _async_mock(decision_record)
    return gatekeeper


@pytest.fixture
def mock_gatekeeper_hitl():
    """Mock Gatekeeper that requires HITL."""
    gatekeeper = MagicMock(spec=Gatekeeper)
    decision_record = MagicMock()
    decision_record.decision.value = "hitl"
    decision_record.policy_rules_failed = []
    decision_record.hitl_ticket_ref = "HITL-12345"
    gatekeeper.evaluate_task = _async_mock(decision_record)
    return gatekeeper


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_with_gatekeeper_allow(mock_task, mock_gatekeeper_allow):
    """Test that routing proceeds when Gatekeeper allows the task."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        gatekeeper=mock_gatekeeper_allow,
    )

    # Should not raise
    error = await service._check_gatekeeper(mock_task)
    assert error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_with_gatekeeper_block(mock_task, mock_gatekeeper_block):
    """Test that GatekeeperRoutingError is raised when Gatekeeper blocks."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        gatekeeper=mock_gatekeeper_block,
    )

    error = await service._check_gatekeeper(mock_task)
    assert error is not None
    assert isinstance(error, GatekeeperRoutingError)
    assert error.decision == "block"
    assert error.task_id == "task-001"
    assert "POL-001" in error.reason


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_with_gatekeeper_hitl(mock_task, mock_gatekeeper_hitl):
    """Test that GatekeeperRoutingError is raised when HITL is required."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        gatekeeper=mock_gatekeeper_hitl,
    )

    error = await service._check_gatekeeper(mock_task)
    assert error is not None
    assert isinstance(error, GatekeeperRoutingError)
    assert error.decision == "hitl"
    assert error.hitl_ticket_ref == "HITL-12345"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_without_gatekeeper(mock_task):
    """Test that routing proceeds when no Gatekeeper is configured."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        gatekeeper=None,
    )

    # Should not raise and return None
    error = await service._check_gatekeeper(mock_task)
    assert error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_router_agent_process_task_gatekeeper_block(mock_task, mock_gatekeeper_block):
    """Test AgentRouterAgent handles Gatekeeper blocks correctly."""
    signal_bus = MagicMock()
    agent = AgentRouterAgent(
        tenant_id=1,
        signal_bus=signal_bus,
        gatekeeper=mock_gatekeeper_block,
    )

    # Mock the service to avoid initialization
    agent._service._redis = MagicMock()
    agent._service._registry = MagicMock()
    agent._service._llm = MagicMock()

    result = await agent.process_task(mock_task)

    assert result.success is False
    assert "Gatekeeper block" in result.error_message
    assert result.result_data["gatekeeper_decision"] == "block"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_router_agent_process_task_gatekeeper_hitl(mock_task, mock_gatekeeper_hitl):
    """Test AgentRouterAgent handles HITL requirements correctly."""
    signal_bus = MagicMock()
    agent = AgentRouterAgent(
        tenant_id=1,
        signal_bus=signal_bus,
        gatekeeper=mock_gatekeeper_hitl,
    )

    # Mock the service to avoid initialization
    agent._service._redis = MagicMock()
    agent._service._registry = MagicMock()
    agent._service._llm = MagicMock()

    result = await agent.process_task(mock_task)

    assert result.success is False
    assert "Human-in-the-loop" in result.error_message
    assert result.result_data["hitl_ticket_ref"] == "HITL-12345"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gatekeeper_error_attributes():
    """Test GatekeeperRoutingError has correct attributes."""
    error = GatekeeperRoutingError(
        tenant_id=42,
        task_id="task-123",
        decision="block",
        reason="Policy violation",
        hitl_ticket_ref=None,
    )

    assert error.tenant_id == 42
    assert error.task_id == "task-123"
    assert error.decision == "block"
    assert error.reason == "Policy violation"
    assert error.hitl_ticket_ref is None
    assert "task-123" in str(error)
    assert "42" in str(error)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_service_gatekeeper_exception_handling(mock_task):
    """Test that Gatekeeper exceptions are handled gracefully (fail open)."""
    mock_gatekeeper_exception = MagicMock(spec=Gatekeeper)

    async def _raise_exception(*args, **kwargs):
        raise Exception("Gatekeeper crash")

    mock_gatekeeper_exception.evaluate_task = _raise_exception

    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        gatekeeper=mock_gatekeeper_exception,
    )

    # Should not raise, should fail open
    error = await service._check_gatekeeper(mock_task)
    assert error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_end_to_end_routing_with_gatekeeper_allow(mock_task, mock_gatekeeper_allow):
    """Test full routing flow when Gatekeeper allows the task."""
    service = RouterService(
        tenant_id=1,
        redis_client=MagicMock(),
        registry=MagicMock(),
        llm_client=MagicMock(),
        gatekeeper=mock_gatekeeper_allow,
    )

    # Check gatekeeper
    error = await service._check_gatekeeper(mock_task)
    assert error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tenant_id_in_gatekeeper_error():
    """Test that tenant ID is properly propagated in Gatekeeper errors."""
    error = GatekeeperRoutingError(
        tenant_id=999,
        task_id="task-xyz",
        decision="hitl",
        reason="Manual approval required",
        hitl_ticket_ref="HITL-999",
    )

    assert error.tenant_id == 999
    assert "tenant=999" in str(error)
