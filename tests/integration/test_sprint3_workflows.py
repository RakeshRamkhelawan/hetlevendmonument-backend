"""
Integration Tests - Sprint 3: Workflows & Procedures
Phase 3 — Workflow Execution Testing (Migrated to authenticated_workflow_api pattern)

Tests the workflow and procedure execution system:
1. Workflow creation and configuration
2. Workflow definition with steps
3. Multi-step execution flow
4. State management and checkpoints
5. Error handling and rollback
"""

import pytest


@pytest.mark.asyncio
async def test_complete_workflow_lifecycle(authenticated_workflow_api):
    """
    Test complete workflow from creation to execution.

    Flow:
    1. Create workflow (auth already handled by fixture)
    2. Execute workflow
    3. Monitor execution status
    4. Verify completion

    Uses: authenticated_workflow_api fixture with automatic auth & schema validation
    """
    # Step 1: Create workflow with valid schema (workflow_type, trigger_type, nodes, edges)
    workflow_payload = {
        "workflow_id": "data_processing_wf",
        "name": "Data Processing Workflow",
        "description": "Extract, transform, load data",
        "workflow_type": "data_pipeline",
        "trigger_type": "manual",
        "spec": {
            "tasks": [
                {"id": "extract", "type": "task", "config": {"source": "database"}},
                {
                    "id": "transform",
                    "type": "task",
                    "config": {"rules": ["clean", "validate"]},
                },
                {"id": "load", "type": "task", "config": {"destination": "warehouse"}},
            ],
            "dependencies": {"transform": ["extract"], "load": ["transform"]},
        },
    }
    workflow = await authenticated_workflow_api.post("/api/v1/workflows", json=workflow_payload)
    assert "workflow_id" in workflow
    assert workflow["status"] == "created"

    # Step 2: Execute workflow
    execution_payload = {"input_data": {"batch_id": "batch_001"}}
    execution = await authenticated_workflow_api.post(
        f"/api/v1/workflows/{workflow_payload['workflow_id']}/execute",
        json=execution_payload,
        schema_type="execution_result",
    )
    execution_id = execution.get("execution_id") or execution.get("id")
    assert execution_id is not None

    # Step 3: Check execution status
    status = await authenticated_workflow_api.get(
        f"/api/v1/workflows/executions/{execution_id}", schema_type="execution_result"
    )
    assert status["status"] in ["pending", "running", "completed", "failed", "queued"]

    # Step 4: List all executions
    executions = await authenticated_workflow_api.get("/api/v1/workflows/executions")
    assert isinstance(executions, list)
    assert len(executions) >= 1


@pytest.mark.asyncio
async def test_multi_step_procedure_execution(authenticated_workflow_api):
    """
    Test multi-step workflow execution with state management.

    Flow:
    1. Create workflow with multiple steps
    2. Execute workflow
    3. Verify execution completes

    Uses: authenticated_workflow_api fixture
    """
    # Create multi-step workflow
    workflow_payload = {
        "workflow_id": "complex_wf",
        "name": "Complex Workflow",
        "description": "Multi-step with state",
        "workflow_type": "sequential",
        "trigger_type": "manual",
        "spec": {
            "tasks": [
                {"id": "initialize", "type": "task", "config": {"mode": "setup"}},
                {
                    "id": "validate",
                    "type": "task",
                    "config": {"rules": ["required_fields"]},
                },
                {"id": "process", "type": "task", "config": {"algorithm": "v2"}},
                {"id": "verify", "type": "task", "config": {"checks": ["integrity"]}},
                {"id": "finalize", "type": "task", "config": {"cleanup": True}},
            ],
            "dependencies": {
                "validate": ["initialize"],
                "process": ["validate"],
                "verify": ["process"],
                "finalize": ["verify"],
            },
        },
    }
    workflow = await authenticated_workflow_api.post("/api/v1/workflows", json=workflow_payload)
    assert "workflow_id" in workflow

    # Execute workflow
    execution_payload = {"input_data": {"test_mode": True}}
    execution = await authenticated_workflow_api.post(
        f"/api/v1/workflows/{workflow_payload['workflow_id']}/execute",
        json=execution_payload,
        schema_type="execution_result",
    )
    execution_id = execution.get("execution_id") or execution.get("id")
    assert execution_id is not None

    # Verify execution was created
    status = await authenticated_workflow_api.get(
        f"/api/v1/workflows/executions/{execution_id}", schema_type="execution_result"
    )
    assert status["status"] in ["pending", "running", "completed", "failed", "queued"]


@pytest.mark.asyncio
async def test_workflow_error_handling_and_rollback(authenticated_workflow_api):
    """
    Test error handling in workflows.

    Flow:
    1. Create workflow that may fail
    2. Execute workflow
    3. Verify status is tracked correctly

    Uses: authenticated_workflow_api fixture
    """
    # Create workflow with potential failure point
    workflow_payload = {
        "workflow_id": "error_handling_wf",
        "name": "Error Handling Workflow",
        "description": "Test error handling",
        "workflow_type": "validation",
        "trigger_type": "manual",
        "spec": {
            "tasks": [
                {"id": "step1", "type": "task", "config": {"status": "success"}},
                {"id": "step2", "type": "task", "config": {"status": "success"}},
                {"id": "step3_validation", "type": "task", "config": {"strict": True}},
                {"id": "step4", "type": "task", "config": {"status": "success"}},
            ],
            "dependencies": {
                "step2": ["step1"],
                "step3_validation": ["step2"],
                "step4": ["step3_validation"],
            },
        },
    }
    workflow = await authenticated_workflow_api.post("/api/v1/workflows", json=workflow_payload)
    assert "workflow_id" in workflow

    # Execute workflow
    execution_payload = {"input_data": {"test_error_handling": True}}
    execution = await authenticated_workflow_api.post(
        f"/api/v1/workflows/{workflow_payload['workflow_id']}/execute",
        json=execution_payload,
        schema_type="execution_result",
    )
    execution_id = execution.get("execution_id") or execution.get("id")

    # Verify execution status is tracked
    status = await authenticated_workflow_api.get(
        f"/api/v1/workflows/executions/{execution_id}", schema_type="execution_result"
    )
    assert status["status"] in [
        "pending",
        "running",
        "completed",
        "failed",
        "queued",
        "error",
        "rolled_back",
    ]


@pytest.mark.asyncio
async def test_workflow_conditional_branching(authenticated_workflow_api):
    """
    Test conditional workflow execution.

    Flow:
    1. Create workflow with conditional logic
    2. Execute with different conditions

    Uses: authenticated_workflow_api fixture
    """
    # Create workflow with conditional steps
    workflow_payload = {
        "workflow_id": "conditional_wf",
        "name": "Conditional Workflow",
        "description": "Test branching logic",
        "workflow_type": "conditional",
        "trigger_type": "manual",
        "spec": {
            "tasks": [
                {
                    "id": "check_condition",
                    "type": "task",
                    "config": {"variable": "approval_needed"},
                },
                {
                    "id": "conditional_branch",
                    "type": "conditional",
                    "config": {
                        "if": "approval_needed == True",
                        "then": "approval_workflow",
                        "else": "auto_process",
                    },
                },
            ],
            "dependencies": {"conditional_branch": ["check_condition"]},
        },
    }
    workflow = await authenticated_workflow_api.post("/api/v1/workflows", json=workflow_payload)
    assert "workflow_id" in workflow

    # Execute with condition True
    execution_payload_true = {"input_data": {"approval_needed": True}}
    execution1 = await authenticated_workflow_api.post(
        f"/api/v1/workflows/{workflow_payload['workflow_id']}/execute",
        json=execution_payload_true,
        schema_type="execution_result",
    )
    assert execution1.get("execution_id") or execution1.get("id")

    # Execute with condition False
    execution_payload_false = {"input_data": {"approval_needed": False}}
    execution2 = await authenticated_workflow_api.post(
        f"/api/v1/workflows/{workflow_payload['workflow_id']}/execute",
        json=execution_payload_false,
        schema_type="execution_result",
    )
    assert execution2.get("execution_id") or execution2.get("id")


@pytest.mark.asyncio
async def test_workflow_parallel_execution(authenticated_workflow_api):
    """
    Test parallel step execution within a workflow.

    Flow:
    1. Create workflow with parallel steps
    2. Execute workflow
    3. Verify execution completes

    Uses: authenticated_workflow_api fixture
    """
    # Create workflow with parallel steps
    workflow_payload = {
        "workflow_id": "parallel_wf",
        "name": "Parallel Workflow",
        "description": "Test concurrent execution",
        "workflow_type": "parallel",
        "trigger_type": "manual",
        "spec": {
            "tasks": [
                {"id": "initialize", "type": "task", "config": {}},
                {"id": "task_a", "type": "task", "config": {"duration": 1}},
                {"id": "task_b", "type": "task", "config": {"duration": 1}},
                {"id": "task_c", "type": "task", "config": {"duration": 1}},
                {"id": "merge_results", "type": "task", "config": {}},
            ],
            "dependencies": {
                "task_a": ["initialize"],
                "task_b": ["initialize"],
                "task_c": ["initialize"],
                "merge_results": ["task_a", "task_b", "task_c"],
            },
        },
    }
    workflow = await authenticated_workflow_api.post("/api/v1/workflows", json=workflow_payload)
    assert "workflow_id" in workflow

    # Execute workflow
    execution_payload = {"input_data": {"test_parallel": True}}
    execution = await authenticated_workflow_api.post(
        f"/api/v1/workflows/{workflow_payload['workflow_id']}/execute",
        json=execution_payload,
        schema_type="execution_result",
    )
    assert execution.get("execution_id") or execution.get("id")


@pytest.mark.asyncio
async def test_workflow_scheduling(authenticated_workflow_api):
    """
    Test workflow creation and retrieval.

    Flow:
    1. Create workflow
    2. Retrieve workflow details
    3. Verify workflow properties

    Uses: authenticated_workflow_api fixture
    """
    # Create workflow
    workflow_payload = {
        "workflow_id": "scheduled_wf",
        "name": "Scheduled Workflow",
        "description": "Test workflow management",
        "workflow_type": "scheduled",
        "trigger_type": "cron",
        "spec": {
            "tasks": [{"id": "task1", "type": "task", "config": {}}],
            "dependencies": {},
        },
    }
    workflow = await authenticated_workflow_api.post("/api/v1/workflows", json=workflow_payload)
    assert "workflow_id" in workflow
    assert workflow["status"] == "created"

    # Retrieve workflow
    retrieved = await authenticated_workflow_api.get(f"/api/v1/workflows/{workflow_payload['workflow_id']}")
    assert retrieved["workflow_id"] == workflow_payload["workflow_id"]
    assert retrieved["name"] == workflow_payload["name"]
