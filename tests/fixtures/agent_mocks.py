"""
tests/fixtures/agent_mocks.py - Agent System Mocks

Provides mock implementations for agent runtime, registry, and pool.
All mocks are deterministic, async-compatible, and thread-safe.

KEY PRINCIPLES:
1. In-memory state management (no external dependencies)
2. Deterministic execution (configurable responses)
3. Thread-safe operations
4. Full type hints

Created: 2025-12-11
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from unittest.mock import AsyncMock

import pytest

# ============================================================================
# AGENT STATE ENUMS
# ============================================================================


class AgentStatus(str, Enum):
    """Agent execution status."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# FAKE AGENT RUNTIME
# ============================================================================


@dataclass
class AgentExecutionResult:
    """Result of agent execution."""

    agent_id: str
    status: AgentStatus
    output: Any
    error: Optional[str] = None
    execution_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class FakeAgentRuntime:
    """
    Mock agent runtime for testing agent execution.

    Simulates agent execution with configurable responses.
    No actual AI/LLM calls - all responses are pre-configured.

    Example:
        >>> runtime = FakeAgentRuntime(responses={
        ...     "agent1": {"status": "completed", "output": "Result 1"},
        ... })
        >>> result = await runtime.execute("agent1", {"input": "test"})
        >>> assert result.status == AgentStatus.COMPLETED
        >>> assert result.output == "Result 1"
    """

    def __init__(
        self,
        responses: Optional[Dict[str, Dict[str, Any]]] = None,
        default_response: Optional[Dict[str, Any]] = None,
        execution_delay_ms: int = 0,
    ):
        """
        Initialize FakeAgentRuntime.

        Args:
            responses: Dict mapping agent_id to execution results
            default_response: Fallback response if agent_id not found
            execution_delay_ms: Simulated execution delay (for testing timeouts)
        """
        self.responses = responses or {}
        self.default_response = default_response or {
            "status": "completed",
            "output": "Mock agent output",
        }
        self.execution_delay_ms = execution_delay_ms

        # State tracking
        self.running_agents: Set[str] = set()
        self.execution_log: List[Dict[str, Any]] = []
        self.call_count = 0

    async def execute(
        self,
        agent_id: str,
        input_data: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        **kwargs,
    ) -> AgentExecutionResult:
        """
        Execute agent with input data.

        Args:
            agent_id: Unique agent identifier
            input_data: Input parameters for agent
            timeout_ms: Execution timeout (raises asyncio.TimeoutError if exceeded)
            **kwargs: Additional execution parameters

        Returns:
            AgentExecutionResult with status and output

        Raises:
            asyncio.TimeoutError: If execution exceeds timeout_ms
        """
        self.call_count += 1
        start_time = datetime.now(timezone.utc)

        # Log execution
        self.execution_log.append(
            {
                "agent_id": agent_id,
                "input": input_data,
                "kwargs": kwargs,
                "timestamp": start_time,
            }
        )

        # Mark as running
        self.running_agents.add(agent_id)

        try:
            # Simulate execution delay
            if self.execution_delay_ms > 0:
                if timeout_ms and self.execution_delay_ms > timeout_ms:
                    raise asyncio.TimeoutError(f"Agent {agent_id} execution timeout")
                await asyncio.sleep(self.execution_delay_ms / 1000)

            # Get response (agent-specific or default)
            response_config = self.responses.get(agent_id, self.default_response)

            # Build result
            status_str = response_config.get("status", "completed")
            result = AgentExecutionResult(
                agent_id=agent_id,
                status=AgentStatus(status_str),
                output=response_config.get("output", "Mock output"),
                error=response_config.get("error"),
                execution_time_ms=self.execution_delay_ms,
                metadata={
                    "call_count": self.call_count,
                    "input": input_data,
                },
            )

            return result

        finally:
            # Mark as no longer running
            self.running_agents.discard(agent_id)

    async def cancel(self, agent_id: str) -> bool:
        """
        Cancel running agent execution.

        Returns:
            True if agent was running and cancelled, False otherwise
        """
        if agent_id in self.running_agents:
            self.running_agents.remove(agent_id)
            return True
        return False

    def is_running(self, agent_id: str) -> bool:
        """Check if agent is currently running."""
        return agent_id in self.running_agents

    def set_response(self, agent_id: str, response: Dict[str, Any]):
        """Configure response for specific agent."""
        self.responses[agent_id] = response

    def reset(self):
        """Reset all state."""
        self.running_agents.clear()
        self.execution_log.clear()
        self.call_count = 0


# ============================================================================
# MOCK AGENT REGISTRY
# ============================================================================


@dataclass
class RegisteredAgent:
    """Agent metadata in registry."""

    agent_id: str
    name: str
    agent_type: str
    capabilities: List[str] = field(default_factory=list)
    status: str = "active"
    metadata: Dict[str, Any] = field(default_factory=dict)


class MockAgentRegistry:
    """
    In-memory agent registry for testing.

    Stores agent metadata without external dependencies.

    Example:
        >>> registry = MockAgentRegistry()
        >>> await registry.register("agent1", "Test Agent", "core")
        >>> agent = await registry.get("agent1")
        >>> assert agent.name == "Test Agent"
    """

    def __init__(self):
        """Initialize empty registry."""
        self.agents: Dict[str, RegisteredAgent] = {}
        self.call_log: List[Dict[str, Any]] = []

    async def register(
        self,
        agent_id: str,
        name: str,
        agent_type: str,
        capabilities: Optional[List[str]] = None,
        **metadata,
    ) -> RegisteredAgent:
        """
        Register new agent.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable agent name
            agent_type: Agent classification (core, specialist, etc.)
            capabilities: List of agent capabilities
            **metadata: Additional metadata

        Returns:
            RegisteredAgent instance
        """
        self.call_log.append(
            {
                "action": "register",
                "agent_id": agent_id,
                "name": name,
            }
        )

        agent = RegisteredAgent(
            agent_id=agent_id,
            name=name,
            agent_type=agent_type,
            capabilities=capabilities or [],
            status="active",
            metadata=metadata,
        )

        self.agents[agent_id] = agent
        return agent

    async def get(self, agent_id: str) -> Optional[RegisteredAgent]:
        """Get agent by ID."""
        self.call_log.append({"action": "get", "agent_id": agent_id})
        return self.agents.get(agent_id)

    async def list_agents(
        self,
        agent_type: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[RegisteredAgent]:
        """
        List all registered agents with optional filtering.

        Args:
            agent_type: Filter by agent type
            status: Filter by status

        Returns:
            List of RegisteredAgent instances
        """
        self.call_log.append(
            {
                "action": "list",
                "filters": {"agent_type": agent_type, "status": status},
            }
        )

        agents = list(self.agents.values())

        if agent_type:
            agents = [a for a in agents if a.agent_type == agent_type]
        if status:
            agents = [a for a in agents if a.status == status]

        return agents

    async def deregister(self, agent_id: str) -> bool:
        """
        Remove agent from registry.

        Returns:
            True if agent was removed, False if not found
        """
        self.call_log.append({"action": "deregister", "agent_id": agent_id})

        if agent_id in self.agents:
            del self.agents[agent_id]
            return True
        return False

    async def update_status(self, agent_id: str, status: str) -> bool:
        """Update agent status."""
        if agent_id in self.agents:
            self.agents[agent_id].status = status
            return True
        return False

    def reset(self):
        """Clear all agents and logs."""
        self.agents.clear()
        self.call_log.clear()


# ============================================================================
# MOCK AGENT POOL
# ============================================================================


@dataclass
class PoolWorker:
    """Worker in agent pool."""

    worker_id: str
    status: str = "idle"  # idle, busy, offline
    current_task: Optional[str] = None
    tasks_completed: int = 0


class MockAgentPool:
    """
    Mock agent pool without real workers.

    Simulates worker pool behavior for testing concurrency.

    Example:
        >>> pool = MockAgentPool(max_workers=3)
        >>> task_id = await pool.submit("agent1", {"input": "test"})
        >>> result = await pool.get_result(task_id)
    """

    def __init__(self, max_workers: int = 5):
        """
        Initialize pool with N workers.

        Args:
            max_workers: Maximum concurrent workers
        """
        self.max_workers = max_workers
        self.workers: Dict[str, PoolWorker] = {
            f"worker-{i}": PoolWorker(worker_id=f"worker-{i}") for i in range(max_workers)
        }

        self.task_queue: List[Dict[str, Any]] = []
        self.results: Dict[str, Any] = {}
        self.call_log: List[Dict[str, Any]] = []

    async def submit(
        self,
        agent_id: str,
        input_data: Dict[str, Any],
        priority: int = 0,
    ) -> str:
        """
        Submit task to pool.

        Args:
            agent_id: Agent to execute
            input_data: Task input
            priority: Task priority (higher = more important)

        Returns:
            Task ID (UUID)
        """
        task_id = str(uuid.uuid4())

        self.call_log.append(
            {
                "action": "submit",
                "task_id": task_id,
                "agent_id": agent_id,
            }
        )

        # Find idle worker
        idle_worker = next((w for w in self.workers.values() if w.status == "idle"), None)

        if idle_worker:
            # Execute immediately
            idle_worker.status = "busy"
            idle_worker.current_task = task_id

            # Simulate instant completion (this is a mock)
            self.results[task_id] = {
                "status": "completed",
                "output": f"Mock result for {agent_id}",
                "worker_id": idle_worker.worker_id,
            }

            # Mark worker as idle again
            idle_worker.status = "idle"
            idle_worker.current_task = None
            idle_worker.tasks_completed += 1
        else:
            # Queue task (all workers busy)
            self.task_queue.append(
                {
                    "task_id": task_id,
                    "agent_id": agent_id,
                    "input_data": input_data,
                    "priority": priority,
                }
            )

        return task_id

    async def get_result(
        self,
        task_id: str,
        timeout_ms: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get task result (blocking until ready or timeout).

        Args:
            task_id: Task identifier
            timeout_ms: Max wait time in milliseconds

        Returns:
            Task result dict or None if not ready/timeout
        """
        self.call_log.append({"action": "get_result", "task_id": task_id})

        # In mock, results are immediate
        return self.results.get(task_id)

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel pending task."""
        # Remove from queue
        self.task_queue = [t for t in self.task_queue if t["task_id"] != task_id]

        # Mark result as cancelled if exists
        if task_id in self.results:
            self.results[task_id]["status"] = "cancelled"
            return True

        return False

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        idle_workers = sum(1 for w in self.workers.values() if w.status == "idle")
        busy_workers = sum(1 for w in self.workers.values() if w.status == "busy")

        return {
            "total_workers": self.max_workers,
            "idle_workers": idle_workers,
            "busy_workers": busy_workers,
            "queued_tasks": len(self.task_queue),
            "completed_tasks": len(self.results),
        }

    def reset(self):
        """Reset pool state."""
        for worker in self.workers.values():
            worker.status = "idle"
            worker.current_task = None
            worker.tasks_completed = 0

        self.task_queue.clear()
        self.results.clear()
        self.call_log.clear()


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def fake_agent_runtime() -> FakeAgentRuntime:
    """
    Provide FakeAgentRuntime for testing.

    Usage:
        def test_agent(fake_agent_runtime):
            fake_agent_runtime.set_response("agent1", {
                "status": "completed",
                "output": "Test output"
            })
            result = await fake_agent_runtime.execute("agent1", {})
            assert result.status == AgentStatus.COMPLETED
    """
    return FakeAgentRuntime()


@pytest.fixture
def mock_agent_registry() -> MockAgentRegistry:
    """
    Provide MockAgentRegistry for testing.

    Usage:
        async def test_registry(mock_agent_registry):
            await mock_agent_registry.register("a1", "Test", "core")
            agent = await mock_agent_registry.get("a1")
            assert agent.name == "Test"
    """
    return MockAgentRegistry()


@pytest.fixture
def mock_agent_pool() -> MockAgentPool:
    """
    Provide MockAgentPool for testing.

    Usage:
        async def test_pool(mock_agent_pool):
            task_id = await mock_agent_pool.submit("agent1", {})
            result = await mock_agent_pool.get_result(task_id)
            assert result["status"] == "completed"
    """
    return MockAgentPool()


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_fake_runtime(responses: Dict[str, Dict[str, Any]], **kwargs) -> FakeAgentRuntime:
    """
    Factory for creating FakeAgentRuntime with custom config.

    Example:
        >>> runtime = create_fake_runtime(
        ...     responses={"agent1": {"status": "failed", "error": "Test error"}},
        ...     execution_delay_ms=100
        ... )
    """
    return FakeAgentRuntime(responses=responses, **kwargs)
