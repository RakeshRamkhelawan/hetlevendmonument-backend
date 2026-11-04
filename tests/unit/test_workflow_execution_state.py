"""
P5.2.3: Workflow Execution State Transition Tests
==================================================

Tests for valid and invalid state transitions in workflow execution.
Focus on:
- Valid transitions: PENDING → RUNNING → COMPLETED/FAILED/TIMEOUT/CANCELLED
- Invalid transitions (e.g., SUCCEEDED → RUNNING)
- Task state transitions: PENDING → RUNNING → SUCCEEDED/FAILED/RETRYING/SKIPPED
- Terminal state enforcement
- State machine integration with workflow engine

Reference: src/core/workflow/state_machine.py
Reference: src/core/workflow/engine.py

Target Coverage: 95%+
"""

import pytest

from src.core.workflow.models import TaskStatus, WorkflowStatus
from src.core.workflow.state_machine import WorkflowStateMachine, get_state_machine


class TestWorkflowStateTransitions:
    """Test valid and invalid workflow state transitions"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_pending_to_running_valid(self, state_machine):
        """Test valid transition: PENDING → RUNNING"""
        assert state_machine.can_transition("pending", "running", "workflow") is True

    def test_running_to_succeeded_valid(self, state_machine):
        """Test valid transition: RUNNING → SUCCEEDED"""
        assert state_machine.can_transition("running", "succeeded", "workflow") is True

    def test_running_to_failed_valid(self, state_machine):
        """Test valid transition: RUNNING → FAILED"""
        assert state_machine.can_transition("running", "failed", "workflow") is True

    def test_running_to_cancelled_valid(self, state_machine):
        """Test valid transition: RUNNING → CANCELLED"""
        assert state_machine.can_transition("running", "cancelled", "workflow") is True

    def test_running_to_timeout_valid(self, state_machine):
        """Test valid transition: RUNNING → TIMEOUT"""
        assert state_machine.can_transition("running", "timeout", "workflow") is True

    def test_pending_to_cancelled_valid(self, state_machine):
        """Test valid transition: PENDING → CANCELLED (user cancels before start)"""
        assert state_machine.can_transition("pending", "cancelled", "workflow") is True

    def test_pending_to_succeeded_invalid(self, state_machine):
        """Test invalid transition: PENDING → SUCCEEDED (must go through RUNNING)"""
        assert state_machine.can_transition("pending", "succeeded", "workflow") is False

    def test_pending_to_failed_invalid(self, state_machine):
        """Test invalid transition: PENDING → FAILED"""
        assert state_machine.can_transition("pending", "failed", "workflow") is False

    def test_pending_to_timeout_invalid(self, state_machine):
        """Test invalid transition: PENDING → TIMEOUT"""
        assert state_machine.can_transition("pending", "timeout", "workflow") is False

    def test_succeeded_to_running_invalid(self, state_machine):
        """Test invalid transition: SUCCEEDED → RUNNING (terminal state)"""
        assert state_machine.can_transition("succeeded", "running", "workflow") is False

    def test_failed_to_running_invalid(self, state_machine):
        """Test invalid transition: FAILED → RUNNING (terminal state)"""
        assert state_machine.can_transition("failed", "running", "workflow") is False

    def test_cancelled_to_running_invalid(self, state_machine):
        """Test invalid transition: CANCELLED → RUNNING (terminal state)"""
        assert state_machine.can_transition("cancelled", "running", "workflow") is False

    def test_timeout_to_running_invalid(self, state_machine):
        """Test invalid transition: TIMEOUT → RUNNING (terminal state)"""
        assert state_machine.can_transition("timeout", "running", "workflow") is False


class TestTaskStateTransitions:
    """Test task-specific state transitions including retry logic"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_pending_to_running_valid(self, state_machine):
        """Test valid task transition: PENDING → RUNNING"""
        assert state_machine.can_transition("pending", "running", "task") is True

    def test_pending_to_skipped_valid(self, state_machine):
        """Test valid task transition: PENDING → SKIPPED (failed dependency)"""
        assert state_machine.can_transition("pending", "skipped", "task") is True

    def test_running_to_succeeded_valid(self, state_machine):
        """Test valid task transition: RUNNING → SUCCEEDED"""
        assert state_machine.can_transition("running", "succeeded", "task") is True

    def test_running_to_failed_valid(self, state_machine):
        """Test valid task transition: RUNNING → FAILED"""
        assert state_machine.can_transition("running", "failed", "task") is True

    def test_running_to_timeout_valid(self, state_machine):
        """Test valid task transition: RUNNING → TIMEOUT"""
        assert state_machine.can_transition("running", "timeout", "task") is True

    def test_running_to_retrying_valid(self, state_machine):
        """Test valid task transition: RUNNING → RETRYING"""
        assert state_machine.can_transition("running", "retrying", "task") is True

    def test_retrying_to_running_valid(self, state_machine):
        """Test valid task transition: RETRYING → RUNNING (retry attempt)"""
        assert state_machine.can_transition("retrying", "running", "task") is True

    def test_retrying_to_failed_valid(self, state_machine):
        """Test valid task transition: RETRYING → FAILED (exhausted retries)"""
        assert state_machine.can_transition("retrying", "failed", "task") is True

    def test_retrying_to_timeout_valid(self, state_machine):
        """Test valid task transition: RETRYING → TIMEOUT"""
        assert state_machine.can_transition("retrying", "timeout", "task") is True

    def test_failed_to_retrying_valid(self, state_machine):
        """Test valid task transition: FAILED → RETRYING (retry after failure)"""
        assert state_machine.can_transition("failed", "retrying", "task") is True

    def test_succeeded_to_running_invalid(self, state_machine):
        """Test invalid task transition: SUCCEEDED → RUNNING (terminal)"""
        assert state_machine.can_transition("succeeded", "running", "task") is False

    def test_skipped_to_running_invalid(self, state_machine):
        """Test invalid task transition: SKIPPED → RUNNING (terminal)"""
        assert state_machine.can_transition("skipped", "running", "task") is False

    def test_timeout_to_running_invalid(self, state_machine):
        """Test invalid task transition: TIMEOUT → RUNNING (terminal for tasks)"""
        assert state_machine.can_transition("timeout", "running", "task") is False


class TestTerminalStates:
    """Test terminal state enforcement"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_workflow_succeeded_is_terminal(self, state_machine):
        """Test SUCCEEDED is terminal for workflows"""
        assert state_machine.is_terminal_state("succeeded", "workflow") is True
        assert state_machine.get_allowed_transitions("succeeded", "workflow") == []

    def test_workflow_failed_is_terminal(self, state_machine):
        """Test FAILED is terminal for workflows"""
        assert state_machine.is_terminal_state("failed", "workflow") is True
        assert state_machine.get_allowed_transitions("failed", "workflow") == []

    def test_workflow_cancelled_is_terminal(self, state_machine):
        """Test CANCELLED is terminal for workflows"""
        assert state_machine.is_terminal_state("cancelled", "workflow") is True
        assert state_machine.get_allowed_transitions("cancelled", "workflow") == []

    def test_workflow_timeout_is_terminal(self, state_machine):
        """Test TIMEOUT is terminal for workflows"""
        assert state_machine.is_terminal_state("timeout", "workflow") is True
        assert state_machine.get_allowed_transitions("timeout", "workflow") == []

    def test_workflow_pending_not_terminal(self, state_machine):
        """Test PENDING is not terminal for workflows"""
        assert state_machine.is_terminal_state("pending", "workflow") is False
        assert len(state_machine.get_allowed_transitions("pending", "workflow")) > 0

    def test_workflow_running_not_terminal(self, state_machine):
        """Test RUNNING is not terminal for workflows"""
        assert state_machine.is_terminal_state("running", "workflow") is False
        assert len(state_machine.get_allowed_transitions("running", "workflow")) > 0

    def test_task_succeeded_is_terminal(self, state_machine):
        """Test SUCCEEDED is terminal for tasks"""
        assert state_machine.is_terminal_state("succeeded", "task") is True

    def test_task_skipped_is_terminal(self, state_machine):
        """Test SKIPPED is terminal for tasks"""
        assert state_machine.is_terminal_state("skipped", "task") is True

    def test_task_timeout_is_terminal(self, state_machine):
        """Test TIMEOUT is terminal for tasks"""
        assert state_machine.is_terminal_state("timeout", "task") is True

    def test_task_failed_not_terminal(self, state_machine):
        """Test FAILED is NOT terminal for tasks (can retry)"""
        assert state_machine.is_terminal_state("failed", "task") is False
        assert "retrying" in state_machine.get_allowed_transitions("failed", "task")


class TestValidateTransitionExceptions:
    """Test validate_transition raises exceptions for invalid transitions"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_validate_invalid_transition_raises(self, state_machine):
        """Test validate_transition raises ValueError for invalid transition"""
        with pytest.raises(ValueError, match="Invalid.*state transition"):
            state_machine.validate_transition("succeeded", "running", "workflow")

    def test_validate_error_message_includes_from_state(self, state_machine):
        """Test error message includes from_state"""
        with pytest.raises(ValueError, match="succeeded"):
            state_machine.validate_transition("succeeded", "running", "workflow")

    def test_validate_error_message_includes_to_state(self, state_machine):
        """Test error message includes to_state"""
        with pytest.raises(ValueError, match="running"):
            state_machine.validate_transition("succeeded", "running", "workflow")

    def test_validate_error_message_includes_allowed_transitions(self, state_machine):
        """Test error message includes allowed transitions list"""
        with pytest.raises(ValueError, match="Allowed transitions"):
            state_machine.validate_transition("succeeded", "running", "workflow")

    def test_validate_valid_transition_no_exception(self, state_machine):
        """Test validate_transition does not raise for valid transition"""
        try:
            state_machine.validate_transition("pending", "running", "workflow")
        except ValueError:
            pytest.fail("validate_transition raised ValueError for valid transition")


class TestCompleteWorkflowLifecycles:
    """Test complete workflow execution paths"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_successful_workflow_path(self, state_machine):
        """Test successful workflow: PENDING → RUNNING → SUCCEEDED"""
        state_machine.validate_transition("pending", "running", "workflow")
        state_machine.validate_transition("running", "succeeded", "workflow")
        assert state_machine.is_terminal_state("succeeded", "workflow")

    def test_failed_workflow_path(self, state_machine):
        """Test failed workflow: PENDING → RUNNING → FAILED"""
        state_machine.validate_transition("pending", "running", "workflow")
        state_machine.validate_transition("running", "failed", "workflow")
        assert state_machine.is_terminal_state("failed", "workflow")

    def test_cancelled_before_start_path(self, state_machine):
        """Test cancelled workflow: PENDING → CANCELLED"""
        state_machine.validate_transition("pending", "cancelled", "workflow")
        assert state_machine.is_terminal_state("cancelled", "workflow")

    def test_cancelled_during_execution_path(self, state_machine):
        """Test cancelled workflow: PENDING → RUNNING → CANCELLED"""
        state_machine.validate_transition("pending", "running", "workflow")
        state_machine.validate_transition("running", "cancelled", "workflow")
        assert state_machine.is_terminal_state("cancelled", "workflow")

    def test_timeout_workflow_path(self, state_machine):
        """Test timeout workflow: PENDING → RUNNING → TIMEOUT"""
        state_machine.validate_transition("pending", "running", "workflow")
        state_machine.validate_transition("running", "timeout", "workflow")
        assert state_machine.is_terminal_state("timeout", "workflow")


class TestCompleteTaskLifecycles:
    """Test complete task execution paths including retry logic"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_successful_task_path(self, state_machine):
        """Test successful task: PENDING → RUNNING → SUCCEEDED"""
        state_machine.validate_transition("pending", "running", "task")
        state_machine.validate_transition("running", "succeeded", "task")
        assert state_machine.is_terminal_state("succeeded", "task")

    def test_task_with_retry_success(self, state_machine):
        """Test task with retry: PENDING → RUNNING → RETRYING → RUNNING → SUCCEEDED"""
        state_machine.validate_transition("pending", "running", "task")
        state_machine.validate_transition("running", "retrying", "task")
        state_machine.validate_transition("retrying", "running", "task")
        state_machine.validate_transition("running", "succeeded", "task")
        assert state_machine.is_terminal_state("succeeded", "task")

    def test_task_retry_from_failure(self, state_machine):
        """Test task retry after failure: RUNNING → FAILED → RETRYING → RUNNING → SUCCEEDED"""
        state_machine.validate_transition("running", "failed", "task")
        state_machine.validate_transition("failed", "retrying", "task")
        state_machine.validate_transition("retrying", "running", "task")
        state_machine.validate_transition("running", "succeeded", "task")

    def test_task_exhausted_retries(self, state_machine):
        """Test task exhausts retries: RUNNING → RETRYING → FAILED"""
        state_machine.validate_transition("running", "retrying", "task")
        state_machine.validate_transition("retrying", "failed", "task")
        # FAILED is NOT terminal for tasks (can retry)
        assert not state_machine.is_terminal_state("failed", "task")

    def test_task_skipped_path(self, state_machine):
        """Test skipped task: PENDING → SKIPPED (dependency failed)"""
        state_machine.validate_transition("pending", "skipped", "task")
        assert state_machine.is_terminal_state("skipped", "task")

    def test_task_timeout_path(self, state_machine):
        """Test timeout task: PENDING → RUNNING → TIMEOUT"""
        state_machine.validate_transition("pending", "running", "task")
        state_machine.validate_transition("running", "timeout", "task")
        assert state_machine.is_terminal_state("timeout", "task")

    def test_task_retry_then_timeout(self, state_machine):
        """Test task retry then timeout: RUNNING → RETRYING → TIMEOUT"""
        state_machine.validate_transition("running", "retrying", "task")
        state_machine.validate_transition("retrying", "timeout", "task")
        assert state_machine.is_terminal_state("timeout", "task")


class TestGetAllowedTransitions:
    """Test get_allowed_transitions method for all states"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_workflow_pending_allowed_transitions(self, state_machine):
        """Test PENDING workflow allowed transitions"""
        allowed = state_machine.get_allowed_transitions("pending", "workflow")
        assert set(allowed) == {"cancelled", "running"}

    def test_workflow_running_allowed_transitions(self, state_machine):
        """Test RUNNING workflow allowed transitions"""
        allowed = state_machine.get_allowed_transitions("running", "workflow")
        assert set(allowed) == {"cancelled", "failed", "succeeded", "timeout"}

    def test_task_pending_allowed_transitions(self, state_machine):
        """Test PENDING task allowed transitions"""
        allowed = state_machine.get_allowed_transitions("pending", "task")
        assert set(allowed) == {"cancelled", "running", "skipped"}

    def test_task_running_allowed_transitions(self, state_machine):
        """Test RUNNING task allowed transitions"""
        allowed = state_machine.get_allowed_transitions("running", "task")
        assert set(allowed) == {
            "cancelled",
            "failed",
            "retrying",
            "succeeded",
            "timeout",
        }

    def test_task_retrying_allowed_transitions(self, state_machine):
        """Test RETRYING task allowed transitions"""
        allowed = state_machine.get_allowed_transitions("retrying", "task")
        assert set(allowed) == {"cancelled", "failed", "running", "timeout"}

    def test_task_failed_allowed_transitions(self, state_machine):
        """Test FAILED task allowed transitions (can retry)"""
        allowed = state_machine.get_allowed_transitions("failed", "task")
        assert allowed == ["retrying"]

    def test_terminal_state_no_transitions(self, state_machine):
        """Test terminal states have no allowed transitions"""
        assert state_machine.get_allowed_transitions("succeeded", "workflow") == []
        assert state_machine.get_allowed_transitions("succeeded", "task") == []
        assert state_machine.get_allowed_transitions("skipped", "task") == []


class TestCaseInsensitivity:
    """Test state machine handles case variations"""

    @pytest.fixture
    def state_machine(self):
        return WorkflowStateMachine()

    def test_uppercase_states_normalized(self, state_machine):
        """Test uppercase states are normalized to lowercase"""
        assert state_machine.can_transition("PENDING", "RUNNING", "workflow") is True
        assert state_machine.can_transition("RUNNING", "SUCCEEDED", "workflow") is True

    def test_mixed_case_states_normalized(self, state_machine):
        """Test mixed case states are normalized"""
        assert state_machine.can_transition("PeNdInG", "RuNnInG", "workflow") is True

    def test_get_allowed_transitions_case_insensitive(self, state_machine):
        """Test get_allowed_transitions works with any case"""
        allowed_upper = state_machine.get_allowed_transitions("PENDING", "workflow")
        allowed_lower = state_machine.get_allowed_transitions("pending", "workflow")
        assert set(allowed_upper) == set(allowed_lower)

    def test_validate_transition_case_insensitive(self, state_machine):
        """Test validate_transition works with any case"""
        # Should not raise
        state_machine.validate_transition("PENDING", "RUNNING", "workflow")
        state_machine.validate_transition("pending", "running", "workflow")


class TestStateMachineSingleton:
    """Test get_state_machine singleton function"""

    def test_get_state_machine_returns_instance(self):
        """Test get_state_machine returns WorkflowStateMachine instance"""
        sm = get_state_machine()
        assert isinstance(sm, WorkflowStateMachine)

    def test_get_state_machine_singleton_pattern(self):
        """Test get_state_machine returns same instance"""
        sm1 = get_state_machine()
        sm2 = get_state_machine()
        assert sm1 is sm2

    def test_singleton_is_functional(self):
        """Test singleton instance is fully functional"""
        sm = get_state_machine()
        assert sm.can_transition("pending", "running", "workflow") is True
        assert len(sm.get_allowed_transitions("pending", "workflow")) > 0
