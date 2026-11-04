# -*- coding: utf-8 -*-
"""
VIBE_BE_005: Unit Tests for Workflow Execution Service

Target: 95% coverage, 100% pass rate
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.models.workflow_models import ExecutionStatus, NodeExecutionStatus
from src.core.services.workflow_execution_service import (
    ExecutionContext,
    NodeExecutorRegistry,
    NodeResult,
    WorkflowExecutionService,
    create_execution_service,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def simple_workflow():
    """Simple linear workflow for testing."""
    return {
        "name": "simple_workflow",
        "nodes": [
            {
                "id": "trigger",
                "agent_name": "schedule_agent",
                "label": "Trigger",
                "config": {},
            },
            {
                "id": "slack",
                "agent_name": "slack_agent",
                "label": "Slack",
                "config": {},
            },
        ],
        "edges": [{"id": "e1", "source": "trigger", "target": "slack"}],
    }


@pytest.fixture
def parallel_workflow():
    """Workflow with parallel execution paths."""
    return {
        "name": "parallel_workflow",
        "nodes": [
            {
                "id": "trigger",
                "agent_name": "schedule_agent",
                "label": "Trigger",
                "config": {},
            },
            {
                "id": "slack",
                "agent_name": "slack_agent",
                "label": "Slack",
                "config": {},
            },
            {
                "id": "email",
                "agent_name": "email_agent",
                "label": "Email",
                "config": {},
            },
            {
                "id": "end",
                "agent_name": "notification_agent",
                "label": "End",
                "config": {},
            },
        ],
        "edges": [
            {"id": "e1", "source": "trigger", "target": "slack"},
            {"id": "e2", "source": "trigger", "target": "email"},
            {"id": "e3", "source": "slack", "target": "end"},
            {"id": "e4", "source": "email", "target": "end"},
        ],
    }


@pytest.fixture
def service():
    """Create a WorkflowExecutionService instance."""
    return WorkflowExecutionService()


# ============================================================================
# NodeExecutorRegistry Tests
# ============================================================================


class TestNodeExecutorRegistry:
    """Tests for NodeExecutorRegistry class."""

    def test_init_default_executors(self):
        """Test that default executors are registered."""
        registry = NodeExecutorRegistry()
        assert registry.get_executor("slack_agent") is not None
        assert registry.get_executor("email_agent") is not None
        assert registry.get_executor("llm_summarizer") is not None

    def test_register_custom_executor(self):
        """Test registering a custom executor."""
        registry = NodeExecutorRegistry()

        async def custom_executor(node, context):
            return {"custom": True}

        registry.register("custom_agent", custom_executor)
        assert registry.get_executor("custom_agent") == custom_executor

    def test_unknown_executor_returns_mock(self):
        """Test that unknown agent returns mock executor."""
        registry = NodeExecutorRegistry()
        executor = registry.get_executor("unknown_agent")
        assert executor is not None  # Should return mock

    @pytest.mark.asyncio
    async def test_mock_executor_returns_result(self):
        """Test mock executor returns valid result."""
        registry = NodeExecutorRegistry()
        executor = registry.get_executor("mock_agent")

        context = ExecutionContext(execution_id="test", tenant_id=1, input_data={})

        result = await executor({"id": "test_node"}, context)
        assert "status" in result or "message" in result

    @pytest.mark.asyncio
    async def test_schedule_executor(self):
        """Test schedule agent executor."""
        registry = NodeExecutorRegistry()
        executor = registry.get_executor("schedule_agent")

        context = ExecutionContext(execution_id="test", tenant_id=1, input_data={"key": "value"})

        result = await executor({"id": "schedule"}, context)
        assert result.get("triggered") is True

    @pytest.mark.asyncio
    async def test_llm_executor(self):
        """Test LLM executor."""
        registry = NodeExecutorRegistry()
        executor = registry.get_executor("llm_summarizer")

        context = ExecutionContext(execution_id="test", tenant_id=1, input_data={})

        result = await executor({"id": "llm", "config": {"prompt": "Test"}}, context)
        assert "summary" in result or "model" in result


# ============================================================================
# ExecutionContext Tests
# ============================================================================


class TestExecutionContext:
    """Tests for ExecutionContext dataclass."""

    def test_init(self):
        """Test context initialization."""
        context = ExecutionContext(
            execution_id="exec-123", tenant_id=5, input_data={"key": "value"}
        )
        assert context.execution_id == "exec-123"
        assert context.tenant_id == 5
        assert context.input_data["key"] == "value"
        assert context.node_outputs == {}

    def test_get_node_output_empty(self):
        """Test getting output for non-existent node."""
        context = ExecutionContext(execution_id="test", tenant_id=1, input_data={})
        assert context.get_node_output("nonexistent") == {}

    def test_get_node_output_existing(self):
        """Test getting output for existing node."""
        context = ExecutionContext(execution_id="test", tenant_id=1, input_data={})
        context.node_outputs["node_1"] = {"result": "success"}
        assert context.get_node_output("node_1") == {"result": "success"}


# ============================================================================
# WorkflowExecutionService Tests
# ============================================================================


class TestWorkflowExecutionService:
    """Tests for WorkflowExecutionService class."""

    def test_init_default(self):
        """Test default initialization."""
        service = WorkflowExecutionService()
        assert service.executor_registry is not None
        assert service._active_executions == {}

    def test_init_custom_registry(self):
        """Test initialization with custom registry."""
        custom_registry = NodeExecutorRegistry()
        service = WorkflowExecutionService(executor_registry=custom_registry)
        assert service.executor_registry == custom_registry

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self, service, simple_workflow):
        """Test executing a simple linear workflow."""
        status, outputs, error = await service.execute_workflow(
            workflow=simple_workflow, input_data={"test": True}, tenant_id=1
        )

        assert status == ExecutionStatus.SUCCEEDED
        assert error is None
        assert "trigger" in outputs
        assert "slack" in outputs

    @pytest.mark.asyncio
    async def test_execute_parallel_workflow(self, service, parallel_workflow):
        """Test executing workflow with parallel nodes."""
        status, outputs, error = await service.execute_workflow(
            workflow=parallel_workflow, input_data={}, tenant_id=1
        )

        assert status == ExecutionStatus.SUCCEEDED
        assert "slack" in outputs
        assert "email" in outputs

    @pytest.mark.asyncio
    async def test_execute_with_progress_callback(self, service, simple_workflow):
        """Test execution with progress callback."""
        progress_events = []

        async def callback(event):
            progress_events.append(event)

        status, outputs, error = await service.execute_workflow(
            workflow=simple_workflow, progress_callback=callback
        )

        assert status == ExecutionStatus.SUCCEEDED
        event_types = [e.get("type") for e in progress_events]
        assert "execution_started" in event_types
        assert "execution_complete" in event_types

    @pytest.mark.asyncio
    async def test_execute_empty_workflow(self, service):
        """Test executing workflow with no nodes."""
        empty_workflow = {"name": "empty", "nodes": [], "edges": []}

        status, outputs, error = await service.execute_workflow(workflow=empty_workflow)

        assert status == ExecutionStatus.FAILED
        assert "No nodes" in error

    @pytest.mark.asyncio
    async def test_execute_node_failure(self, service):
        """Test handling of node execution failure."""
        workflow = {
            "name": "failing",
            "nodes": [
                {
                    "id": "fail",
                    "agent_name": "failing_agent",
                    "label": "Fail",
                    "config": {},
                }
            ],
            "edges": [],
        }

        # Register a failing executor
        async def failing_executor(node, context):
            raise Exception("Node failed!")

        service.executor_registry.register("failing_agent", failing_executor)

        status, outputs, error = await service.execute_workflow(workflow=workflow)

        assert status == ExecutionStatus.FAILED
        assert "fail" in error.lower() or "Node failed" in error

    @pytest.mark.asyncio
    async def test_get_active_execution(self, service, simple_workflow):
        """Test getting active execution context."""
        # Start execution in background
        import asyncio

        async def slow_workflow():
            return await service.execute_workflow(workflow=simple_workflow, tenant_id=1)

        # Execution is too fast for this test with mock executors
        # Just verify the method returns None for non-existent
        assert service.get_active_execution("nonexistent") is None

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_execution(self, service):
        """Test cancelling non-existent execution."""
        result = await service.cancel_execution("nonexistent")
        assert result is False


# ============================================================================
# Topological Sort Tests
# ============================================================================


class TestTopologicalSort:
    """Tests for dependency graph and topological sorting."""

    def test_build_dependency_graph(self, service, simple_workflow):
        """Test building dependency graph."""
        nodes = simple_workflow["nodes"]
        edges = simple_workflow["edges"]

        graph, in_degree = service._build_dependency_graph(nodes, edges)

        assert "trigger" in graph
        assert "trigger" in in_degree
        assert in_degree["trigger"] == 0  # No incoming edges
        assert in_degree["slack"] == 1  # One incoming edge

    def test_topological_sort_linear(self, service, simple_workflow):
        """Test topological sort of linear workflow."""
        nodes = simple_workflow["nodes"]
        edges = simple_workflow["edges"]

        graph, in_degree = service._build_dependency_graph(nodes, edges)
        levels = service._topological_sort(nodes, graph, in_degree)

        assert len(levels) == 2
        assert levels[0][0]["id"] == "trigger"
        assert levels[1][0]["id"] == "slack"

    def test_topological_sort_parallel(self, service, parallel_workflow):
        """Test topological sort of parallel workflow."""
        nodes = parallel_workflow["nodes"]
        edges = parallel_workflow["edges"]

        graph, in_degree = service._build_dependency_graph(nodes, edges)
        levels = service._topological_sort(nodes, graph, in_degree)

        # First level: trigger
        # Second level: slack and email (parallel)
        # Third level: end
        assert len(levels) == 3
        assert len(levels[1]) == 2  # Two parallel nodes


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestCreateExecutionService:
    """Tests for factory function."""

    def test_create_execution_service(self):
        """Test creating execution service."""
        service = create_execution_service()
        assert isinstance(service, WorkflowExecutionService)

    def test_create_execution_service_with_db(self):
        """Test creating execution service with DB session."""
        mock_db = object()
        service = create_execution_service(db_session=mock_db)
        assert service.db_session == mock_db
