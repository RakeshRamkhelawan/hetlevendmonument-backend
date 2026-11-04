"""Tests for Workflow Engine - Fase 2.3"""

from datetime import datetime

import pytest

from src.core.agents.workflow_engine import (
    TaskPriority,
    TaskStatus,
    WorkflowEngine,
    WorkflowExecutionMode,
    get_workflow_engine,
)


class TestWorkflowEngine:
    """Test suite for Workflow Engine"""

    @pytest.fixture
    def engine(self):
        """Create fresh workflow engine for each test"""
        return WorkflowEngine()

    def test_create_workflow(self, engine):
        """Test workflow creation"""
        workflow_id = engine.create_workflow(
            name="Test Workflow",
            description="Test workflow description",
            execution_mode=WorkflowExecutionMode.SEQUENTIAL,
        )

        assert workflow_id is not None
        assert workflow_id.startswith("workflow_")
        assert workflow_id in engine.workflows

        workflow = engine.get_workflow(workflow_id)
        assert workflow.name == "Test Workflow"
        assert workflow.execution_mode == WorkflowExecutionMode.SEQUENTIAL

    def test_add_task_to_workflow(self, engine):
        """Test adding task to workflow"""
        workflow_id = engine.create_workflow(
            name="Test Workflow",
            description="Test",
            execution_mode=WorkflowExecutionMode.SEQUENTIAL,
        )

        task_id = engine.add_task(
            workflow_id=workflow_id,
            name="Test Task",
            description="Task description",
            agent_type="code",
            parameters={"test": "value"},
            priority=TaskPriority.HIGH,
        )

        assert task_id is not None
        assert task_id.startswith("task_")

        workflow = engine.get_workflow(workflow_id)
        assert len(workflow.tasks) == 1
        assert workflow.tasks[0].name == "Test Task"
        assert workflow.tasks[0].priority == TaskPriority.HIGH

    def test_workflow_validation(self, engine):
        """Test workflow dependency validation"""
        workflow_id = engine.create_workflow(
            name="Test Workflow",
            description="Test",
            execution_mode=WorkflowExecutionMode.SEQUENTIAL,
        )

        # Add task with invalid dependency
        task_id = engine.add_task(
            workflow_id=workflow_id,
            name="Test Task",
            description="Task",
            agent_type="code",
            parameters={},
            dependencies=["invalid_task_id"],
        )

        workflow = engine.get_workflow(workflow_id)
        errors = engine._validate_dependencies(workflow)

        assert len(errors) > 0
        assert "invalid dependency" in errors[0].lower()

    def test_execution_plan_building(self, engine):
        """Test execution plan generation"""
        workflow_id = engine.create_workflow(
            name="Test Workflow",
            description="Test",
            execution_mode=WorkflowExecutionMode.SEQUENTIAL,
        )

        # Add tasks with dependencies
        task1_id = engine.add_task(
            workflow_id=workflow_id,
            name="Task 1",
            description="First task",
            agent_type="code",
            parameters={},
        )

        task2_id = engine.add_task(
            workflow_id=workflow_id,
            name="Task 2",
            description="Second task",
            agent_type="code",
            parameters={},
            dependencies=[task1_id],
        )

        workflow = engine.get_workflow(workflow_id)
        execution_plan = engine._build_execution_plan(workflow)

        assert len(execution_plan) == 2
        assert task1_id in execution_plan[0]
        assert task2_id in execution_plan[1]

    def test_get_workflow_stats(self, engine):
        """Test workflow statistics retrieval"""
        # Create multiple workflows
        for i in range(3):
            engine.create_workflow(
                name=f"Workflow {i}",
                description="Test",
                execution_mode=WorkflowExecutionMode.SEQUENTIAL,
            )

        stats = engine.get_workflow_stats()

        assert stats["total_workflows"] >= 3  # May have more from singleton
        assert "total_executions" in stats
        assert "subagents_available" in stats
        assert isinstance(stats["subagents_available"], int)

    def test_list_workflows(self, engine):
        """Test listing all workflows"""
        workflow_ids = []
        for i in range(3):
            wf_id = engine.create_workflow(
                name=f"Workflow {i}",
                description="Test",
                execution_mode=WorkflowExecutionMode.PARALLEL,
            )
            workflow_ids.append(wf_id)

        workflows = engine.list_workflows()

        assert len(workflows) == 3
        retrieved_ids = [wf.workflow_id for wf in workflows]
        assert set(workflow_ids) == set(retrieved_ids)

    def test_workflow_execution_modes(self, engine):
        """Test different workflow execution modes"""
        modes = [
            WorkflowExecutionMode.SEQUENTIAL,
            WorkflowExecutionMode.PARALLEL,
            WorkflowExecutionMode.MIXED,
        ]

        for mode in modes:
            workflow_id = engine.create_workflow(
                name=f"Test {mode.value}", description="Test", execution_mode=mode
            )

            workflow = engine.get_workflow(workflow_id)
            assert workflow.execution_mode == mode

    def test_get_workflow_engine_singleton(self):
        """Test global workflow engine singleton"""
        engine1 = get_workflow_engine()
        engine2 = get_workflow_engine()

        assert engine1 is engine2
        assert isinstance(engine1, WorkflowEngine)


@pytest.mark.asyncio
class TestWorkflowEngineAsync:
    """Async tests for Workflow Engine"""

    @pytest.fixture
    def engine(self):
        """Create fresh workflow engine"""
        return WorkflowEngine()

    async def test_execute_workflow_validation_error(self, engine):
        """Test workflow execution with validation errors"""
        workflow_id = engine.create_workflow(
            name="Invalid Workflow",
            description="Test",
            execution_mode=WorkflowExecutionMode.SEQUENTIAL,
        )

        # Add task with invalid dependency
        engine.add_task(
            workflow_id=workflow_id,
            name="Task",
            description="Test",
            agent_type="code",
            parameters={},
            dependencies=["invalid"],
        )

        with pytest.raises(ValueError, match="validation failed"):
            await engine.execute_workflow(workflow_id)
