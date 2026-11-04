"""
P4.6.2: Workflows Domain - Comprehensive Test Coverage
Tests workflow step validation, DAG (Directed Acyclic Graph), and execution
Target: 80%+ coverage on src/domains/workflows/
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.domains.workflows.models import Workflow, WorkflowStatus, WorkflowStep


class TestWorkflowStep:
    """Test WorkflowStep model"""

    def test_workflow_step_creation_minimal(self):
        """Test creating workflow step with minimal fields"""
        step = WorkflowStep(id="step_1", name="Step One", step_type="action", order=0)
        assert step.id == "step_1"
        assert step.name == "Step One"
        assert step.step_type == "action"
        assert step.order == 0
        assert step.status == WorkflowStatus.PENDING
        assert step.dependencies == []

    def test_workflow_step_with_config(self):
        """Test workflow step with configuration"""
        config = {"timeout": 30, "retries": 3}
        step = WorkflowStep(
            id="step_config",
            name="Configured Step",
            step_type="agent_call",
            order=1,
            config=config,
        )
        assert step.config == config

    def test_workflow_step_with_dependencies(self):
        """Test workflow step with dependencies"""
        dependencies = ["step_0", "step_1"]
        step = WorkflowStep(
            id="step_depends",
            name="Dependent Step",
            step_type="join",
            order=2,
            dependencies=dependencies,
        )
        assert step.dependencies == dependencies

    def test_workflow_step_with_result(self):
        """Test workflow step with execution result"""
        result = {"output": "success", "data": [1, 2, 3]}
        step = WorkflowStep(
            id="step_result",
            name="Result Step",
            step_type="action",
            order=0,
            result=result,
            status=WorkflowStatus.COMPLETED,
        )
        assert step.result == result
        assert step.status == WorkflowStatus.COMPLETED

    def test_workflow_step_equality(self):
        """Test workflow step equality based on ID"""
        step1 = WorkflowStep(id="same_id", name="Step A", step_type="action", order=0)
        step2 = WorkflowStep(id="same_id", name="Step B", step_type="different", order=5)
        assert step1 == step2  # Same ID = equal

    def test_workflow_step_empty_config(self):
        """Test workflow step with empty config"""
        step = WorkflowStep(
            id="empty_config",
            name="Empty Config",
            step_type="action",
            order=0,
            config={},
        )
        assert step.config == {}

    def test_workflow_step_none_result(self):
        """Test workflow step with no result"""
        step = WorkflowStep(id="no_result", name="No Result", step_type="action", order=0)
        assert step.result is None


class TestWorkflowModel:
    """Test Workflow aggregate root"""

    def test_workflow_creation_minimal(self):
        """Test creating workflow with minimal fields"""
        workflow = Workflow(id="workflow_1", name="Simple Workflow", tenant_id="tenant_1")
        assert workflow.id == "workflow_1"
        assert workflow.name == "Simple Workflow"
        assert workflow.tenant_id == "tenant_1"
        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.steps == []

    def test_workflow_with_description(self):
        """Test workflow with description"""
        workflow = Workflow(
            id="workflow_desc",
            name="Described Workflow",
            description="This is a test workflow",
            tenant_id="tenant_1",
        )
        assert workflow.description == "This is a test workflow"

    def test_workflow_with_metadata(self):
        """Test workflow with metadata"""
        metadata = {"version": 1, "author": "test_user"}
        workflow = Workflow(
            id="workflow_meta",
            name="Metadata Workflow",
            tenant_id="tenant_1",
            metadata=metadata,
        )
        assert workflow.metadata == metadata

    def test_workflow_add_step(self):
        """Test adding step to workflow"""
        workflow = Workflow(id="workflow_add", name="Step Addition", tenant_id="tenant_1")
        step = WorkflowStep(id="step_1", name="First Step", step_type="action", order=0)
        workflow.add_step(step)
        assert len(workflow.steps) == 1
        assert workflow.steps[0].id == "step_1"

    def test_workflow_add_multiple_steps(self):
        """Test adding multiple steps to workflow"""
        workflow = Workflow(id="workflow_multi", name="Multi Step", tenant_id="tenant_1")
        steps = [
            WorkflowStep(id=f"step_{i}", name=f"Step {i}", step_type="action", order=i)
            for i in range(5)
        ]
        for step in steps:
            workflow.add_step(step)

        assert len(workflow.steps) == 5
        assert all(workflow.steps[i].id == f"step_{i}" for i in range(5))

    def test_workflow_start_from_pending(self):
        """Test starting workflow from PENDING status"""
        workflow = Workflow(
            id="workflow_start",
            name="Starting Workflow",
            tenant_id="tenant_1",
            status=WorkflowStatus.PENDING,
        )
        workflow.start()
        assert workflow.status == WorkflowStatus.RUNNING

    def test_workflow_start_emits_event(self):
        """Test workflow start emits domain event"""
        workflow = Workflow(id="workflow_event", name="Event Workflow", tenant_id="tenant_1")
        workflow.start()
        events = workflow.get_domain_events()
        assert any(e["type"] == "workflow.started" for e in events)

    def test_workflow_start_from_running_raises_error(self):
        """Test starting workflow already running raises error"""
        workflow = Workflow(
            id="workflow_running",
            name="Running Workflow",
            tenant_id="tenant_1",
            status=WorkflowStatus.RUNNING,
        )
        with pytest.raises(ValueError, match="Cannot start workflow"):
            workflow.start()

    def test_workflow_start_from_completed_raises_error(self):
        """Test starting completed workflow raises error"""
        workflow = Workflow(
            id="workflow_completed",
            name="Completed",
            tenant_id="tenant_1",
            status=WorkflowStatus.COMPLETED,
        )
        with pytest.raises(ValueError):
            workflow.start()

    def test_workflow_complete(self):
        """Test completing workflow"""
        workflow = Workflow(
            id="workflow_complete",
            name="Completing",
            tenant_id="tenant_1",
            status=WorkflowStatus.RUNNING,
        )
        result = {"status": "success", "output": "done"}
        workflow.complete(result)
        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.metadata["result"] == result

    def test_workflow_complete_emits_event(self):
        """Test workflow completion emits event"""
        workflow = Workflow(
            id="workflow_complete_event",
            name="Completing",
            tenant_id="tenant_1",
            status=WorkflowStatus.RUNNING,
        )
        workflow.complete({"data": "result"})
        events = workflow.get_domain_events()
        assert any(e["type"] == "workflow.completed" for e in events)

    def test_workflow_fail(self):
        """Test marking workflow as failed"""
        workflow = Workflow(
            id="workflow_fail",
            name="Failing",
            tenant_id="tenant_1",
            status=WorkflowStatus.RUNNING,
        )
        error_msg = "Agent timeout"
        workflow.fail(error_msg)
        assert workflow.status == WorkflowStatus.FAILED
        assert workflow.metadata["error"] == error_msg

    def test_workflow_fail_emits_event(self):
        """Test workflow failure emits event"""
        workflow = Workflow(id="workflow_fail_event", name="Failing", tenant_id="tenant_1")
        workflow.fail("Test error")
        events = workflow.get_domain_events()
        assert any(e["type"] == "workflow.failed" for e in events)

    def test_workflow_equality(self):
        """Test workflow equality based on ID"""
        w1 = Workflow(id="same_id", name="Workflow A", tenant_id="tenant_1")
        w2 = Workflow(id="same_id", name="Workflow B", tenant_id="tenant_2")
        assert w1 == w2  # Same ID = equal

    def test_workflow_empty_steps(self):
        """Test workflow with empty steps list"""
        workflow = Workflow(id="empty_steps", name="Empty", tenant_id="tenant_1")
        assert workflow.steps == []


class TestWorkflowDAG:
    """Test workflow DAG (Directed Acyclic Graph) validation"""

    def test_workflow_linear_dependency_chain(self):
        """Test workflow with linear dependency chain"""
        workflow = Workflow(id="linear_dag", name="Linear Workflow", tenant_id="tenant_1")

        steps = [
            WorkflowStep(id="step_0", name="Step 0", step_type="start", order=0),
            WorkflowStep(
                id="step_1",
                name="Step 1",
                step_type="action",
                order=1,
                dependencies=["step_0"],
            ),
            WorkflowStep(
                id="step_2",
                name="Step 2",
                step_type="action",
                order=2,
                dependencies=["step_1"],
            ),
            WorkflowStep(
                id="step_3",
                name="Step 3",
                step_type="end",
                order=3,
                dependencies=["step_2"],
            ),
        ]

        for step in steps:
            workflow.add_step(step)

        assert len(workflow.steps) == 4
        assert workflow.steps[1].dependencies == ["step_0"]
        assert workflow.steps[2].dependencies == ["step_1"]

    def test_workflow_parallel_dependencies(self):
        """Test workflow with parallel steps"""
        workflow = Workflow(id="parallel_dag", name="Parallel Workflow", tenant_id="tenant_1")

        steps = [
            WorkflowStep(id="start", name="Start", step_type="start", order=0),
            WorkflowStep(
                id="parallel_1",
                name="Parallel 1",
                step_type="action",
                order=1,
                dependencies=["start"],
            ),
            WorkflowStep(
                id="parallel_2",
                name="Parallel 2",
                step_type="action",
                order=1,
                dependencies=["start"],
            ),
            WorkflowStep(
                id="join",
                name="Join",
                step_type="join",
                order=2,
                dependencies=["parallel_1", "parallel_2"],
            ),
        ]

        for step in steps:
            workflow.add_step(step)

        assert workflow.steps[3].dependencies == ["parallel_1", "parallel_2"]

    def test_workflow_complex_dag(self):
        """Test workflow with complex DAG structure"""
        workflow = Workflow(id="complex_dag", name="Complex Workflow", tenant_id="tenant_1")

        # Build DAG: start -> [A, B] -> C -> [D, E] -> end
        steps = [
            WorkflowStep(id="start", name="Start", step_type="start", order=0),
            WorkflowStep(
                id="A",
                name="Task A",
                step_type="action",
                order=1,
                dependencies=["start"],
            ),
            WorkflowStep(
                id="B",
                name="Task B",
                step_type="action",
                order=1,
                dependencies=["start"],
            ),
            WorkflowStep(
                id="C",
                name="Task C",
                step_type="action",
                order=2,
                dependencies=["A", "B"],
            ),
            WorkflowStep(id="D", name="Task D", step_type="action", order=3, dependencies=["C"]),
            WorkflowStep(id="E", name="Task E", step_type="action", order=3, dependencies=["C"]),
            WorkflowStep(id="end", name="End", step_type="end", order=4, dependencies=["D", "E"]),
        ]

        for step in steps:
            workflow.add_step(step)

        assert len(workflow.steps) == 7
        assert workflow.steps[6].dependencies == ["D", "E"]

    def test_workflow_step_order_integrity(self):
        """Test workflow step ordering is preserved"""
        workflow = Workflow(id="order_test", name="Order Test", tenant_id="tenant_1")

        # Add steps out of order
        steps_unordered = [
            WorkflowStep(id="step_2", name="Step 2", step_type="action", order=2),
            WorkflowStep(id="step_0", name="Step 0", step_type="start", order=0),
            WorkflowStep(id="step_1", name="Step 1", step_type="action", order=1),
        ]

        for step in steps_unordered:
            workflow.add_step(step)

        # Order should be preserved in steps list (insertion order)
        assert workflow.steps[0].id == "step_2"
        assert workflow.steps[1].id == "step_0"
        assert workflow.steps[2].id == "step_1"


class TestWorkflowIntegration:
    """Integration tests for workflow domain"""

    def test_workflow_complete_lifecycle(self):
        """Test complete workflow lifecycle"""
        workflow = Workflow(id="lifecycle", name="Lifecycle Workflow", tenant_id="tenant_1")

        # Add steps
        steps = [
            WorkflowStep(id="s1", name="Step 1", step_type="action", order=0),
            WorkflowStep(id="s2", name="Step 2", step_type="action", order=1, dependencies=["s1"]),
        ]
        for step in steps:
            workflow.add_step(step)

        assert workflow.status == WorkflowStatus.PENDING

        # Start
        workflow.start()
        assert workflow.status == WorkflowStatus.RUNNING

        # Complete
        result = {"success": True}
        workflow.complete(result)
        assert workflow.status == WorkflowStatus.COMPLETED
        assert workflow.metadata["result"] == result

    def test_workflow_failure_path(self):
        """Test workflow failure lifecycle"""
        workflow = Workflow(id="failure_test", name="Failure Workflow", tenant_id="tenant_1")

        workflow.start()
        workflow.fail("Task execution failed")

        assert workflow.status == WorkflowStatus.FAILED
        assert "error" in workflow.metadata

    def test_workflow_domain_events_accumulation(self):
        """Test domain events accumulate through workflow lifecycle"""
        workflow = Workflow(id="events_test", name="Events Workflow", tenant_id="tenant_1")

        workflow.start()
        workflow.complete({"data": "result"})

        events = workflow.get_domain_events()
        assert len(events) >= 2
        event_types = [e["type"] for e in events]
        assert "workflow.started" in event_types
        assert "workflow.completed" in event_types

    def test_workflow_event_data_accuracy(self):
        """Test domain events contain accurate data"""
        workflow = Workflow(id="event_data", name="Event Data Workflow", tenant_id="tenant_1")

        workflow.start()
        events = workflow.get_domain_events()
        start_event = [e for e in events if e["type"] == "workflow.started"][0]

        assert start_event["aggregate_id"] == "event_data"
        assert start_event["data"]["workflow_id"] == "event_data"
        assert start_event["data"]["name"] == "Event Data Workflow"
        assert start_event["data"]["tenant_id"] == "tenant_1"

    def test_multiple_workflow_isolation(self):
        """Test multiple workflows are properly isolated"""
        w1 = Workflow(id="w1", name="Workflow 1", tenant_id="tenant_a")
        w2 = Workflow(id="w2", name="Workflow 2", tenant_id="tenant_b")

        w1.start()
        w2.start()

        assert w1.status == WorkflowStatus.RUNNING
        assert w2.status == WorkflowStatus.RUNNING
        assert w1.tenant_id != w2.tenant_id

    def test_workflow_with_rich_metadata(self):
        """Test workflow with rich metadata throughout lifecycle"""
        metadata = {
            "version": 1,
            "author": "test_user",
            "tags": ["important", "automated"],
        }

        workflow = Workflow(
            id="rich_metadata",
            name="Rich Metadata",
            tenant_id="tenant_1",
            metadata=metadata,
        )

        workflow.start()
        workflow.complete({"status": "success", "duration_ms": 1500})

        # Metadata should be preserved and augmented
        assert workflow.metadata["version"] == 1
        assert "result" in workflow.metadata


class TestWorkflowEdgeCases:
    """Edge case and error handling tests"""

    def test_workflow_empty_description(self):
        """Test workflow with empty description"""
        workflow = Workflow(
            id="empty_desc", name="Empty Desc", tenant_id="tenant_1", description=""
        )
        assert workflow.description == ""

    def test_workflow_none_description(self):
        """Test workflow with None description"""
        workflow = Workflow(id="none_desc", name="None Desc", tenant_id="tenant_1")
        assert workflow.description is None

    def test_workflow_empty_metadata(self):
        """Test workflow with empty metadata"""
        workflow = Workflow(id="empty_meta", name="Empty Meta", tenant_id="tenant_1", metadata={})
        assert workflow.metadata == {}

    def test_workflow_step_with_self_dependency(self):
        """Test workflow step with self-reference in dependencies"""
        # Note: This tests that the model doesn't prevent it
        # In practice, a DAG validator would catch this
        step = WorkflowStep(
            id="self_dep",
            name="Self Dependent",
            step_type="action",
            order=0,
            dependencies=["self_dep"],
        )
        assert "self_dep" in step.dependencies

    def test_workflow_step_large_config(self):
        """Test workflow step with large configuration"""
        large_config = {f"key_{i}": f"value_{i}" * 10 for i in range(100)}
        step = WorkflowStep(
            id="large_config",
            name="Large Config",
            step_type="action",
            order=0,
            config=large_config,
        )
        assert len(step.config) == 100

    def test_workflow_complete_with_complex_result(self):
        """Test workflow completion with nested result data"""
        complex_result = {
            "status": "success",
            "data": {"nested": {"deep": {"value": [1, 2, 3, 4, 5]}}},
            "metrics": {"duration_ms": 1500, "tokens_used": 5000},
        }

        workflow = Workflow(
            id="complex_result",
            name="Complex Result",
            tenant_id="tenant_1",
            status=WorkflowStatus.RUNNING,
        )
        workflow.complete(complex_result)

        assert workflow.metadata["result"]["data"]["nested"]["deep"]["value"] == [
            1,
            2,
            3,
            4,
            5,
        ]

    def test_workflow_fail_with_detailed_error(self):
        """Test workflow failure with detailed error information"""
        error_msg = "Task failed: Agent timeout at step 2, details: connection reset"
        workflow = Workflow(id="detailed_error", name="Detailed Error", tenant_id="tenant_1")
        workflow.fail(error_msg)

        assert error_msg in workflow.metadata["error"]

    def test_workflow_large_step_count(self):
        """Test workflow with many steps"""
        workflow = Workflow(id="large_workflow", name="Large Workflow", tenant_id="tenant_1")

        for i in range(100):
            step = WorkflowStep(
                id=f"step_{i}",
                name=f"Step {i}",
                step_type="action" if i % 2 == 0 else "join",
                order=i,
            )
            workflow.add_step(step)

        assert len(workflow.steps) == 100
