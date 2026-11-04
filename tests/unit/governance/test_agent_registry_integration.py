"""Tests for AgentRegistry OversightGate Integration.

EU AI Act Compliance - Task 4: Agent Registry Integration
Tests for injecting OversightGate into AgentRegistry.distribute_task().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.governance.ai_act_classifier import AIActRiskLevel
from src.core.governance.oversight_gate import OversightGate, OversightResult
from src.core.shared.interfaces import Agent, ExecutionResult, TaskData


@dataclass
class MockAgent:
    """Mock agent for testing."""

    agent_id: str = "test-agent-001"
    agent_type: str = "test"
    _capabilities: List[str] = field(default_factory=list)
    tenant_id: int = 1

    async def get_capabilities(self) -> List[Any]:
        """Return mock capabilities."""
        return []

    async def process_task(self, task: TaskData) -> ExecutionResult:
        """Process task and return success."""
        return ExecutionResult(
            task_id=task.id,
            success=True,
            result_data={"agent_id": self.agent_id, "task": task.title},
            execution_time=0.1,
        )


class MockOversightGate:
    """Mock oversight gate for testing."""

    def __init__(self, result: Optional[OversightResult] = None) -> None:
        self.result = result or OversightResult(
            allowed=True,
            requires_human_approval=False,
            risk_level=AIActRiskLevel.LIMITED,
            reason="Test approval",
        )
        self.check_called = False
        self.last_check_args: Optional[Dict[str, Any]] = None

    async def check(
        self,
        agent_name: str,
        agent_department: str,
        agent_specialisation: str,
        agent_capabilities: List[str],
        task_action: str,
        task_params: Dict[str, Any],
        **kwargs: Any,
    ) -> OversightResult:
        """Mock check method."""
        self.check_called = True
        self.last_check_args = {
            "agent_name": agent_name,
            "agent_department": agent_department,
            "agent_specialisation": agent_specialisation,
            "agent_capabilities": agent_capabilities,
            "task_action": task_action,
            "task_params": task_params,
        }
        return self.result


class TestAgentRegistryGovernanceInit:
    """Test AgentRegistry initializes with OversightGate."""

    def test_registry_accepts_oversight_gate(self) -> None:
        """AgentRegistry should accept OversightGate in constructor."""
        # This will fail until we implement the parameter
        from src.core.agents.agent_registry import AgentRegistry

        mock_gate = MockOversightGate()
        # This should work after implementation
        registry = AgentRegistry(oversight_gate=mock_gate)
        assert registry.oversight_gate is mock_gate


class TestAgentRegistryDistributeTaskGovernance:
    """Test distribute_task with governance checks."""

    @pytest.fixture
    def mock_agent(self) -> MockAgent:
        """Create mock agent."""
        return MockAgent(
            agent_id="test-agent-001",
            agent_type="test",
            _capabilities=["test_capability"],
        )

    @pytest.fixture
    def sample_task(self) -> TaskData:
        """Create sample task."""
        return TaskData(
            id="task-001",
            title="Test Task",
            description="Test task description",
            metadata={
                "agent_id": "test-agent-001",
                "action": "process_data",
                "params": {"data": "test"},
            },
        )

    @pytest.mark.asyncio
    async def test_distribute_task_calls_oversight_check(
        self,
        mock_agent: MockAgent,
        sample_task: TaskData,
    ) -> None:
        """distribute_task should call OversightGate.check()."""
        from src.core.agents.agent_registry import AgentRegistry

        mock_gate = MockOversightGate()
        registry = AgentRegistry(oversight_gate=mock_gate)

        # Register the mock agent
        registry._agents[mock_agent.agent_id] = mock_agent  # type: ignore

        # Distribute task
        result = await registry.distribute_task(sample_task)

        # Verify oversight was consulted
        assert mock_gate.check_called is True

    @pytest.mark.asyncio
    async def test_task_blocked_when_oversight_denies(
        self,
        mock_agent: MockAgent,
        sample_task: TaskData,
    ) -> None:
        """Task should be blocked when OversightGate denies."""
        from src.core.agents.agent_registry import AgentRegistry

        # Create gate that denies all
        mock_gate = MockOversightGate(
            result=OversightResult(
                allowed=False,
                requires_human_approval=False,
                risk_level=AIActRiskLevel.HIGH_RISK,
                reason="Policy violation detected",
            )
        )
        registry = AgentRegistry(oversight_gate=mock_gate)
        registry._agents[mock_agent.agent_id] = mock_agent  # type: ignore

        # Distribute task
        result = await registry.distribute_task(sample_task)

        # Task should be blocked
        assert result is not None
        assert result.success is False
        assert (
            "blocked" in result.error_message.lower()
            or "governance" in result.error_message.lower()
        )

    @pytest.mark.asyncio
    async def test_task_blocked_when_approval_required(
        self,
        mock_agent: MockAgent,
        sample_task: TaskData,
    ) -> None:
        """Task should be blocked pending approval when required."""
        from src.core.agents.agent_registry import AgentRegistry

        mock_gate = MockOversightGate(
            result=OversightResult(
                allowed=True,
                requires_human_approval=True,
                risk_level=AIActRiskLevel.HIGH_RISK,
                reason="High-risk action requires human approval",
            )
        )
        registry = AgentRegistry(oversight_gate=mock_gate)
        registry._agents[mock_agent.agent_id] = mock_agent  # type: ignore

        result = await registry.distribute_task(sample_task)

        assert result is not None
        assert result.success is False
        assert (
            "approval" in result.error_message.lower() or "pending" in result.error_message.lower()
        )

    @pytest.mark.asyncio
    async def test_task_executes_when_oversight_allows(
        self,
        mock_agent: MockAgent,
        sample_task: TaskData,
    ) -> None:
        """Task should execute normally when OversightGate allows."""
        from src.core.agents.agent_registry import AgentRegistry

        mock_gate = MockOversightGate(
            result=OversightResult(
                allowed=True,
                requires_human_approval=False,
                risk_level=AIActRiskLevel.LIMITED,
                reason="Approved for execution",
            )
        )
        registry = AgentRegistry(oversight_gate=mock_gate)
        registry._agents[mock_agent.agent_id] = mock_agent  # type: ignore

        result = await registry.distribute_task(sample_task)

        assert result is not None
        assert result.success is True
        assert result.result_data.get("agent_id") == mock_agent.agent_id


class TestAgentRegistryGovernanceParams:
    """Test that governance receives correct parameters."""

    @pytest.mark.asyncio
    async def test_oversight_receives_agent_info(self) -> None:
        """OversightGate should receive agent metadata."""
        from src.core.agents.agent_registry import AgentRegistry

        mock_gate = MockOversightGate()
        registry = AgentRegistry(oversight_gate=mock_gate)

        mock_agent = MockAgent(agent_id="agent-123", agent_type="specialist")
        registry._agents[mock_agent.agent_id] = mock_agent  # type: ignore

        task = TaskData(
            id="task-456",
            title="Special Task",
            description="Task with metadata",
            metadata={
                "agent_id": "agent-123",
                "department": "HR",
                "specialisation": "recruitment",
            },
        )

        await registry.distribute_task(task)

        # Verify parameters passed to oversight
        assert mock_gate.last_check_args is not None
        assert mock_gate.last_check_args["agent_name"] == "agent-123"
        assert mock_gate.last_check_args["task_action"] == "process_task"


class TestAgentRegistryNoOversight:
    """Test backward compatibility without OversightGate."""

    @pytest.mark.asyncio
    async def test_registry_works_without_oversight_gate(self) -> None:
        """AgentRegistry should work without OversightGate (backward compat)."""
        from src.core.agents.agent_registry import AgentRegistry

        # No oversight gate provided
        registry = AgentRegistry()

        mock_agent = MockAgent()
        registry._agents[mock_agent.agent_id] = mock_agent  # type: ignore

        task = TaskData(
            id="task-001",
            title="Test",
            description="Test",
            metadata={"agent_id": "test-agent-001"},
        )

        # Should execute without error
        result = await registry.distribute_task(task)
        assert result is not None
        assert result.success is True
