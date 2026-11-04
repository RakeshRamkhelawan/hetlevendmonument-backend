"""
Unit tests for MCP Orchestrator
"""

import asyncio
import sys
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.orchestrator.mcp_orchestrator import (
    AgentTask,
    MCPOrchestrator,
    TaskResult,
    TaskStatus,
)
from src.core.tool_broker.mcp_client import MCPClientPool, MCPServerConfig


@pytest.fixture
def mock_mcp_pool():
    """Create mock MCP client pool"""
    pool = Mock(spec=MCPClientPool)
    pool._clients = {}
    pool._configs = {
        "agent1": Mock(name="agent1"),
        "agent2": Mock(name="agent2"),
        "agent3": Mock(name="agent3"),
    }
    return pool


@pytest.fixture
def orchestrator(mock_mcp_pool):
    """Create orchestrator with mock pool"""
    return MCPOrchestrator(mock_mcp_pool)


@pytest.fixture
def sample_tasks() -> List[AgentTask]:
    """Create sample tasks for testing"""
    return [
        AgentTask(task_id="task1", agent_name="agent1", task_description="Task 1", priority=10),
        AgentTask(task_id="task2", agent_name="agent2", task_description="Task 2", priority=5),
        AgentTask(
            task_id="task3",
            agent_name="agent3",
            task_description="Task 3",
            priority=8,
            dependencies=["task1"],
        ),
    ]


class TestAgentTask:
    """Test AgentTask dataclass"""

    def test_create_task(self):
        """Test creating a valid task"""
        task = AgentTask(task_id="test1", agent_name="agent1", task_description="Test task")
        assert task.task_id == "test1"
        assert task.agent_name == "agent1"
        assert task.priority == 0
        assert task.timeout == 120
        assert task.dependencies == []

    def test_task_validation(self):
        """Test task validation"""
        with pytest.raises(ValueError):
            AgentTask(task_id="", agent_name="agent1", task_description="Test")

        with pytest.raises(ValueError):
            AgentTask(task_id="test1", agent_name="", task_description="Test")


class TestTaskResult:
    """Test TaskResult dataclass"""

    def test_successful_result(self):
        """Test successful task result"""
        result = TaskResult(
            task_id="test1",
            agent_name="agent1",
            status=TaskStatus.COMPLETED,
            output={"data": "result"},
            execution_time=5.5,
        )
        assert result.success
        assert result.status == TaskStatus.COMPLETED

    def test_failed_result(self):
        """Test failed task result"""
        result = TaskResult(
            task_id="test1",
            agent_name="agent1",
            status=TaskStatus.FAILED,
            error="Task failed",
            execution_time=2.0,
        )
        assert not result.success
        assert result.error == "Task failed"

    def test_to_dict(self):
        """Test conversion to dictionary"""
        result = TaskResult(
            task_id="test1",
            agent_name="agent1",
            status=TaskStatus.COMPLETED,
            output="success",
            execution_time=3.2,
        )
        data = result.to_dict()
        assert data["task_id"] == "test1"
        assert data["status"] == "completed"
        assert data["success"] is True


class TestDependencyResolution:
    """Test task dependency resolution"""

    def test_sort_no_dependencies(self, orchestrator):
        """Test sorting tasks without dependencies"""
        tasks = [
            AgentTask(
                task_id=f"task{i}",
                agent_name="agent1",
                task_description=f"Task {i}",
                priority=i,
            )
            for i in [5, 2, 8, 1]
        ]

        sorted_tasks = orchestrator._sort_by_dependencies(tasks)
        priorities = [t.priority for t in sorted_tasks]
        assert priorities == [8, 5, 2, 1]  # Descending priority

    def test_sort_with_dependencies(self, orchestrator):
        """Test sorting tasks with dependencies"""
        tasks = [
            AgentTask(
                task_id="task1",
                agent_name="agent1",
                task_description="Task 1",
                dependencies=[],
            ),
            AgentTask(
                task_id="task2",
                agent_name="agent1",
                task_description="Task 2",
                dependencies=["task1"],
            ),
            AgentTask(
                task_id="task3",
                agent_name="agent1",
                task_description="Task 3",
                dependencies=["task1", "task2"],
            ),
        ]

        sorted_tasks = orchestrator._sort_by_dependencies(tasks)
        task_ids = [t.task_id for t in sorted_tasks]

        # task1 must come before task2
        assert task_ids.index("task1") < task_ids.index("task2")
        # task2 must come before task3
        assert task_ids.index("task2") < task_ids.index("task3")

    def test_group_by_dependency_level(self, orchestrator):
        """Test grouping tasks into parallel waves"""
        tasks = [
            AgentTask(
                task_id="task1",
                agent_name="agent1",
                task_description="Task 1",
                dependencies=[],
            ),
            AgentTask(
                task_id="task2",
                agent_name="agent1",
                task_description="Task 2",
                dependencies=[],
            ),
            AgentTask(
                task_id="task3",
                agent_name="agent1",
                task_description="Task 3",
                dependencies=["task1"],
            ),
            AgentTask(
                task_id="task4",
                agent_name="agent1",
                task_description="Task 4",
                dependencies=["task1", "task2"],
            ),
        ]

        waves = orchestrator._group_by_dependency_level(tasks)

        # Wave 1: task1, task2 (no dependencies)
        assert len(waves[0]) == 2
        wave1_ids = {t.task_id for t in waves[0]}
        assert wave1_ids == {"task1", "task2"}

        # Wave 2: task3 and task4 (both can run after wave 1 completes)
        # task3 depends on task1, task4 depends on task1 and task2
        # Since both dependencies are met after wave 1, they can run in parallel
        assert len(waves[1]) == 2
        wave2_ids = {t.task_id for t in waves[1]}
        assert wave2_ids == {"task3", "task4"}


class TestParallelExecution:
    """Test parallel task execution"""

    @pytest.mark.asyncio
    async def test_execute_parallel_empty(self, orchestrator):
        """Test executing empty task list"""
        results = await orchestrator.execute_parallel([])
        assert results == []

    @pytest.mark.asyncio
    async def test_execute_parallel_duplicate_ids(self, orchestrator):
        """Test executing tasks with duplicate IDs"""
        tasks = [
            AgentTask(task_id="task1", agent_name="agent1", task_description="Task 1"),
            AgentTask(task_id="task1", agent_name="agent2", task_description="Task 2"),  # Duplicate
        ]

        with pytest.raises(ValueError, match="Task IDs must be unique"):
            await orchestrator.execute_parallel(tasks)

    @pytest.mark.asyncio
    async def test_execute_parallel_success(self, orchestrator, mock_mcp_pool):
        """Test successful parallel execution"""
        # Setup mock client
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={"result": "success"})

        # Patch MCPClient to return our mock
        with patch("src.core.tool_broker.mcp_client.MCPClient", return_value=mock_client):
            tasks = [
                AgentTask(
                    task_id="task1",
                    agent_name="agent1",
                    task_description="Task 1",
                    timeout=10,
                ),
                AgentTask(
                    task_id="task2",
                    agent_name="agent1",
                    task_description="Task 2",
                    timeout=10,
                ),
            ]

            results = await orchestrator.execute_parallel(tasks, max_concurrent=2)

            assert len(results) == 2
            assert all(r.success for r in results)
            assert all(r.status == TaskStatus.COMPLETED for r in results)

    @pytest.mark.asyncio
    async def test_execute_parallel_timeout(self, orchestrator, mock_mcp_pool):
        """Test parallel execution with timeout"""
        # Setup mock client that times out
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(2)
            return {"result": "too slow"}

        mock_client.call_tool = slow_call

        # Patch MCPClient to return our mock
        with patch("src.core.tool_broker.mcp_client.MCPClient", return_value=mock_client):
            tasks = [
                AgentTask(
                    task_id="task1",
                    agent_name="agent1",
                    task_description="Task 1",
                    timeout=0.1,  # Very short timeout
                ),
            ]

            results = await orchestrator.execute_parallel(tasks)

            assert len(results) == 1
            assert results[0].status == TaskStatus.TIMEOUT
            assert not results[0].success

    @pytest.mark.asyncio
    async def test_execute_parallel_fail_fast(self, orchestrator, mock_mcp_pool):
        """Test fail-fast execution"""
        # Setup mock client that fails
        mock_client = AsyncMock()
        mock_client.call_tool = AsyncMock(side_effect=Exception("Agent error"))
        mock_mcp_pool.get_client = AsyncMock(return_value=mock_client)

        tasks = [
            AgentTask(task_id=f"task{i}", agent_name="agent1", task_description=f"Task {i}")
            for i in range(5)
        ]

        results = await orchestrator.execute_parallel(tasks, max_concurrent=2, fail_fast=True)

        # Some tasks should be marked as failed due to fail-fast
        assert len(results) == 5
        assert any(not r.success for r in results)


class TestSequentialExecution:
    """Test sequential task execution"""

    @pytest.mark.asyncio
    async def test_execute_sequential(self, orchestrator, mock_mcp_pool):
        """Test sequential execution"""
        # Setup mock client
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.call_tool = AsyncMock(return_value={"result": "success"})

        # Patch MCPClient to return our mock
        with patch("src.core.tool_broker.mcp_client.MCPClient", return_value=mock_client):
            tasks = [
                AgentTask(
                    task_id=f"task{i}",
                    agent_name="agent1",
                    task_description=f"Task {i}",
                )
                for i in range(3)
            ]

            results = await orchestrator.execute_sequential(tasks)

            assert len(results) == 3
            assert all(r.success for r in results)

            # Verify call_tool was called 3 times
            assert mock_client.call_tool.call_count == 3


class TestAgentRegistration:
    """Test agent registration"""

    @pytest.mark.asyncio
    async def test_register_agent(self, orchestrator, mock_mcp_pool):
        """Test registering an agent"""
        config = MCPServerConfig(name="test_agent", command="python", args=["-m", "test_agent"])

        await orchestrator.register_agent(config)

        # Verify pool.register was called
        mock_mcp_pool.register.assert_called_once_with(config)


class TestActiveTaskTracking:
    """Test active task tracking"""

    @pytest.mark.asyncio
    async def test_get_active_tasks(self, orchestrator):
        """Test getting active tasks"""
        # Initially empty
        active = await orchestrator.get_active_tasks()
        assert active == []

        # Add some tasks manually
        orchestrator.active_tasks["task1"] = AgentTask(
            task_id="task1", agent_name="agent1", task_description="Task 1"
        )

        active = await orchestrator.get_active_tasks()
        assert len(active) == 1
        assert active[0].task_id == "task1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
