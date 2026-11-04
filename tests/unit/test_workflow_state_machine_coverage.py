"""
Comprehensive test coverage for Workflow State Machine (95%+ coverage target)

Tests specifically target missing lines: 81, 101-111, 131-132, 148-149, 158
Current coverage: 60.71% (11 lines missed)
Target: 95%+ coverage
"""

import pytest

from src.core.workflow.interfaces import IStateMachine
from src.core.workflow.state_machine import WorkflowStateMachine, get_state_machine


class TestWorkflowBasicTransitions:
    """Test basic workflow state transitions (lines 70-100+)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_pending_to_running_allowed(self, sm):
        """Test PENDING → RUNNING is allowed"""
        assert sm.can_transition("pending", "running", "workflow") is True

    def test_pending_to_cancelled_allowed(self, sm):
        """Test PENDING → CANCELLED is allowed"""
        assert sm.can_transition("pending", "cancelled", "workflow") is True

    def test_running_to_succeeded_allowed(self, sm):
        """Test RUNNING → SUCCEEDED is allowed"""
        assert sm.can_transition("running", "succeeded", "workflow") is True

    def test_running_to_failed_allowed(self, sm):
        """Test RUNNING → FAILED is allowed"""
        assert sm.can_transition("running", "failed", "workflow") is True

    def test_running_to_cancelled_allowed(self, sm):
        """Test RUNNING → CANCELLED is allowed"""
        assert sm.can_transition("running", "cancelled", "workflow") is True

    def test_running_to_timeout_allowed(self, sm):
        """Test RUNNING → TIMEOUT is allowed"""
        assert sm.can_transition("running", "timeout", "workflow") is True

    def test_invalid_transition_pending_to_succeeded(self, sm):
        """Test invalid transition PENDING → SUCCEEDED"""
        assert sm.can_transition("pending", "succeeded", "workflow") is False

    def test_invalid_transition_pending_to_failed(self, sm):
        """Test invalid transition PENDING → FAILED"""
        assert sm.can_transition("pending", "failed", "workflow") is False


class TestWorkflowTerminalStates:
    """Test workflow terminal states (no transitions)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_succeeded_is_terminal(self, sm):
        """Test SUCCEEDED is terminal"""
        assert sm.can_transition("succeeded", "running", "workflow") is False
        assert sm.can_transition("succeeded", "failed", "workflow") is False
        assert sm.can_transition("succeeded", "cancelled", "workflow") is False
        assert sm.can_transition("succeeded", "timeout", "workflow") is False

    def test_failed_is_terminal(self, sm):
        """Test FAILED is terminal"""
        assert sm.can_transition("failed", "running", "workflow") is False
        assert sm.can_transition("failed", "succeeded", "workflow") is False
        assert sm.can_transition("failed", "cancelled", "workflow") is False

    def test_cancelled_is_terminal(self, sm):
        """Test CANCELLED is terminal"""
        assert sm.can_transition("cancelled", "running", "workflow") is False
        assert sm.can_transition("cancelled", "pending", "workflow") is False

    def test_timeout_is_terminal(self, sm):
        """Test TIMEOUT is terminal"""
        assert sm.can_transition("timeout", "running", "workflow") is False
        assert sm.can_transition("timeout", "succeeded", "workflow") is False


class TestInvalidSourceState:
    """Test can_transition with invalid from_status (line 81)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_invalid_from_status_returns_false(self, sm):
        """Test invalid from_status returns False (line 81)"""
        assert sm.can_transition("invalid_status", "running", "workflow") is False

    def test_gibberish_from_status(self, sm):
        """Test gibberish from_status"""
        assert sm.can_transition("xyz", "running", "workflow") is False

    def test_empty_from_status(self, sm):
        """Test empty from_status"""
        assert sm.can_transition("", "running", "workflow") is False

    def test_none_like_from_status(self, sm):
        """Test None-like string from_status"""
        assert sm.can_transition("none", "running", "workflow") is False

    def test_numeric_from_status(self, sm):
        """Test numeric from_status"""
        assert sm.can_transition("123", "running", "workflow") is False


class TestTaskBasicTransitions:
    """Test basic task state transitions"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_task_pending_to_running(self, sm):
        """Test task PENDING → RUNNING"""
        assert sm.can_transition("pending", "running", "task") is True

    def test_task_pending_to_skipped(self, sm):
        """Test task PENDING → SKIPPED"""
        assert sm.can_transition("pending", "skipped", "task") is True

    def test_task_running_to_succeeded(self, sm):
        """Test task RUNNING → SUCCEEDED"""
        assert sm.can_transition("running", "succeeded", "task") is True

    def test_task_running_to_failed(self, sm):
        """Test task RUNNING → FAILED"""
        assert sm.can_transition("running", "failed", "task") is True

    def test_task_running_to_timeout(self, sm):
        """Test task RUNNING → TIMEOUT"""
        assert sm.can_transition("running", "timeout", "task") is True

    def test_task_running_to_retrying(self, sm):
        """Test task RUNNING → RETRYING (line 101-111)"""
        assert sm.can_transition("running", "retrying", "task") is True

    def test_task_retrying_to_running(self, sm):
        """Test task RETRYING → RUNNING (retry loop)"""
        assert sm.can_transition("retrying", "running", "task") is True

    def test_task_retrying_to_failed(self, sm):
        """Test task RETRYING → FAILED"""
        assert sm.can_transition("retrying", "failed", "task") is True

    def test_task_retrying_to_timeout(self, sm):
        """Test task RETRYING → TIMEOUT"""
        assert sm.can_transition("retrying", "timeout", "task") is True


class TestTaskRetryFlow:
    """Test task retry/failure flow"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_task_failed_can_retry(self, sm):
        """Test task FAILED → RETRYING (line 101-111)"""
        assert sm.can_transition("failed", "retrying", "task") is True

    def test_task_failed_cannot_go_directly_to_running(self, sm):
        """Test task FAILED cannot go directly to RUNNING"""
        assert sm.can_transition("failed", "running", "task") is False

    def test_task_failed_to_other_states(self, sm):
        """Test task FAILED cannot transition to non-retrying states"""
        assert sm.can_transition("failed", "succeeded", "task") is False
        assert sm.can_transition("failed", "skipped", "task") is False


class TestTaskTerminalStates:
    """Test task terminal states"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_task_succeeded_is_terminal(self, sm):
        """Test task SUCCEEDED is terminal"""
        assert sm.can_transition("succeeded", "running", "task") is False
        assert sm.can_transition("succeeded", "failed", "task") is False

    def test_task_skipped_is_terminal(self, sm):
        """Test task SKIPPED is terminal"""
        assert sm.can_transition("skipped", "running", "task") is False
        assert sm.can_transition("skipped", "pending", "task") is False

    def test_task_timeout_is_terminal(self, sm):
        """Test task TIMEOUT is terminal"""
        assert sm.can_transition("timeout", "running", "task") is False


class TestGetAllowedTransitionsWorkflow:
    """Test get_allowed_transitions for workflows (lines 101-111)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_pending_allows_running_and_cancelled(self, sm):
        """Test PENDING workflow allows running and cancelled"""
        allowed = sm.get_allowed_transitions("pending", "workflow")
        assert set(allowed) == {"running", "cancelled"}

    def test_running_allows_all_terminal_states(self, sm):
        """Test RUNNING workflow allows multiple terminal states"""
        allowed = sm.get_allowed_transitions("running", "workflow")
        assert "succeeded" in allowed
        assert "failed" in allowed
        assert "cancelled" in allowed
        assert "timeout" in allowed
        assert len(allowed) == 4

    def test_succeeded_has_no_transitions(self, sm):
        """Test SUCCEEDED workflow has no transitions"""
        allowed = sm.get_allowed_transitions("succeeded", "workflow")
        assert allowed == []

    def test_failed_has_no_transitions(self, sm):
        """Test FAILED workflow has no transitions"""
        allowed = sm.get_allowed_transitions("failed", "workflow")
        assert allowed == []

    def test_cancelled_has_no_transitions(self, sm):
        """Test CANCELLED workflow has no transitions"""
        allowed = sm.get_allowed_transitions("cancelled", "workflow")
        assert allowed == []

    def test_timeout_has_no_transitions(self, sm):
        """Test TIMEOUT workflow has no transitions"""
        allowed = sm.get_allowed_transitions("timeout", "workflow")
        assert allowed == []

    def test_invalid_status_returns_empty_list(self, sm):
        """Test invalid status returns empty list"""
        allowed = sm.get_allowed_transitions("invalid", "workflow")
        assert allowed == []

    def test_returned_transitions_are_sorted(self, sm):
        """Test returned transitions are sorted"""
        allowed = sm.get_allowed_transitions("running", "workflow")
        assert allowed == sorted(allowed)


class TestGetAllowedTransitionsTask:
    """Test get_allowed_transitions for tasks (lines 101-111)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_task_pending_allows_running_and_skipped(self, sm):
        """Test task PENDING allows running, skipped, and cancelled"""
        allowed = sm.get_allowed_transitions("pending", "task")
        assert set(allowed) == {"running", "skipped", "cancelled"}

    def test_task_running_allows_multiple_states(self, sm):
        """Test task RUNNING allows multiple states"""
        allowed = sm.get_allowed_transitions("running", "task")
        assert "succeeded" in allowed
        assert "failed" in allowed
        assert "timeout" in allowed
        assert "retrying" in allowed

    def test_task_retrying_allows_retry_flow(self, sm):
        """Test task RETRYING allows retry flow"""
        allowed = sm.get_allowed_transitions("retrying", "task")
        assert set(allowed) == {"running", "failed", "timeout", "cancelled"}

    def test_task_failed_allows_retry(self, sm):
        """Test task FAILED allows retrying (line 101-111)"""
        allowed = sm.get_allowed_transitions("failed", "task")
        assert allowed == ["retrying"]

    def test_task_succeeded_has_no_transitions(self, sm):
        """Test task SUCCEEDED has no transitions"""
        allowed = sm.get_allowed_transitions("succeeded", "task")
        assert allowed == []

    def test_task_skipped_has_no_transitions(self, sm):
        """Test task SKIPPED has no transitions"""
        allowed = sm.get_allowed_transitions("skipped", "task")
        assert allowed == []


class TestValidateTransitionSuccess:
    """Test validate_transition doesn't raise for valid transitions"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_valid_workflow_transitions_no_exception(self, sm):
        """Test valid workflow transitions don't raise"""
        sm.validate_transition("pending", "running", "workflow")
        sm.validate_transition("running", "succeeded", "workflow")
        sm.validate_transition("running", "failed", "workflow")
        sm.validate_transition("pending", "cancelled", "workflow")

    def test_valid_task_transitions_no_exception(self, sm):
        """Test valid task transitions don't raise"""
        sm.validate_transition("pending", "running", "task")
        sm.validate_transition("running", "retrying", "task")
        sm.validate_transition("retrying", "running", "task")
        sm.validate_transition("failed", "retrying", "task")


class TestValidateTransitionErrors:
    """Test validate_transition raises for invalid transitions (lines 131-132)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_invalid_workflow_transition_raises(self, sm):
        """Test invalid workflow transition raises ValueError"""
        with pytest.raises(ValueError) as exc:
            sm.validate_transition("succeeded", "running", "workflow")

        error = str(exc.value)
        assert "Invalid workflow state transition" in error
        assert "succeeded -> running" in error

    def test_invalid_task_transition_raises(self, sm):
        """Test invalid task transition raises ValueError"""
        with pytest.raises(ValueError) as exc:
            sm.validate_transition("succeeded", "running", "task")

        error = str(exc.value)
        assert "Invalid task state transition" in error
        assert "succeeded -> running" in error

    def test_error_includes_allowed_transitions(self, sm):
        """Test error message includes allowed transitions (line 131-132)"""
        with pytest.raises(ValueError) as exc:
            sm.validate_transition("pending", "failed", "workflow")

        error = str(exc.value)
        assert "Allowed transitions from 'pending'" in error
        assert "running" in error
        assert "cancelled" in error

    def test_invalid_from_status_error(self, sm):
        """Test error for invalid from_status"""
        with pytest.raises(ValueError) as exc:
            sm.validate_transition("invalid_status", "running", "workflow")

        error = str(exc.value)
        assert "Invalid workflow state transition" in error

    def test_multiple_invalid_transitions_raise(self, sm):
        """Test multiple invalid transitions all raise"""
        invalid_pairs = [
            ("succeeded", "running"),
            ("failed", "pending"),
            ("cancelled", "running"),
            ("timeout", "failed"),
        ]

        for from_status, to_status in invalid_pairs:
            with pytest.raises(ValueError):
                sm.validate_transition(from_status, to_status, "workflow")


class TestIsTerminalStateWorkflow:
    """Test is_terminal_state for workflows (lines 148-149)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_workflow_terminal_states(self, sm):
        """Test workflow terminal states are recognized"""
        assert sm.is_terminal_state("succeeded", "workflow") is True
        assert sm.is_terminal_state("failed", "workflow") is True
        assert sm.is_terminal_state("cancelled", "workflow") is True
        assert sm.is_terminal_state("timeout", "workflow") is True

    def test_workflow_non_terminal_states(self, sm):
        """Test workflow non-terminal states"""
        assert sm.is_terminal_state("pending", "workflow") is False
        assert sm.is_terminal_state("running", "workflow") is False

    def test_workflow_invalid_state_not_terminal(self, sm):
        """Test invalid state behavior"""
        # Invalid states return True (no outgoing transitions)
        result = sm.is_terminal_state("invalid_state", "workflow")
        assert result is True


class TestIsTerminalStateTask:
    """Test is_terminal_state for tasks (lines 148-149)"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_task_terminal_states(self, sm):
        """Test task terminal states are recognized"""
        assert sm.is_terminal_state("succeeded", "task") is True
        assert sm.is_terminal_state("timeout", "task") is True
        assert sm.is_terminal_state("skipped", "task") is True

    def test_task_non_terminal_states(self, sm):
        """Test task non-terminal states"""
        assert sm.is_terminal_state("pending", "task") is False
        assert sm.is_terminal_state("running", "task") is False
        assert sm.is_terminal_state("retrying", "task") is False
        assert sm.is_terminal_state("failed", "task") is False  # Can retry failed tasks

    def test_task_retrying_not_terminal_even_with_few_transitions(self, sm):
        """Test RETRYING is not terminal even though it has limited transitions"""
        allowed = sm.get_allowed_transitions("retrying", "task")
        is_terminal = sm.is_terminal_state("retrying", "task")

        # RETRYING has transitions, so it's not terminal
        assert len(allowed) > 0
        assert is_terminal is False


class TestGetStateMachineSingleton:
    """Test get_state_machine singleton function (line 158)"""

    def test_returns_state_machine_instance(self):
        """Test get_state_machine returns WorkflowStateMachine"""
        sm = get_state_machine()
        assert isinstance(sm, WorkflowStateMachine)

    def test_returns_same_instance(self):
        """Test get_state_machine returns same instance (singleton)"""
        sm1 = get_state_machine()
        sm2 = get_state_machine()
        sm3 = get_state_machine()

        assert sm1 is sm2
        assert sm2 is sm3
        assert sm1 is sm3

    def test_singleton_implements_interface(self):
        """Test singleton implements IStateMachine"""
        sm = get_state_machine()
        assert isinstance(sm, IStateMachine)

    def test_singleton_has_all_methods(self):
        """Test singleton has all expected methods"""
        sm = get_state_machine()
        assert callable(sm.can_transition)
        assert callable(sm.get_allowed_transitions)
        assert callable(sm.validate_transition)
        assert callable(sm.is_terminal_state)

    def test_singleton_is_functional(self):
        """Test singleton instance works correctly"""
        sm = get_state_machine()

        assert sm.can_transition("pending", "running", "workflow")
        assert not sm.can_transition("succeeded", "running", "workflow")

        allowed = sm.get_allowed_transitions("pending", "workflow")
        assert "running" in allowed

        assert sm.is_terminal_state("succeeded", "workflow")


class TestCaseInsensitivity:
    """Test case handling in all methods"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_can_transition_uppercase(self, sm):
        """Test can_transition with uppercase"""
        assert sm.can_transition("PENDING", "RUNNING", "workflow") is True

    def test_can_transition_mixed_case(self, sm):
        """Test can_transition with mixed case"""
        assert sm.can_transition("PeNdInG", "RuNnInG", "workflow") is True

    def test_get_allowed_transitions_uppercase(self, sm):
        """Test get_allowed_transitions with uppercase"""
        allowed = sm.get_allowed_transitions("RUNNING", "workflow")
        assert len(allowed) > 0
        assert all(s.islower() for s in allowed)  # Results are lowercase

    def test_validate_transition_uppercase(self, sm):
        """Test validate_transition with uppercase"""
        # Should not raise
        sm.validate_transition("PENDING", "RUNNING", "workflow")

    def test_is_terminal_state_uppercase(self, sm):
        """Test is_terminal_state with uppercase"""
        assert sm.is_terminal_state("SUCCEEDED", "workflow") is True
        assert sm.is_terminal_state("PENDING", "workflow") is False


class TestCompleteWorkflowLifecycles:
    """Test complete realistic workflow execution paths"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_successful_workflow_path(self, sm):
        """Test successful workflow: PENDING → RUNNING → SUCCEEDED"""
        sm.validate_transition("pending", "running", "workflow")
        sm.validate_transition("running", "succeeded", "workflow")
        assert sm.is_terminal_state("succeeded", "workflow")

    def test_failed_workflow_path(self, sm):
        """Test failed workflow: PENDING → RUNNING → FAILED"""
        sm.validate_transition("pending", "running", "workflow")
        sm.validate_transition("running", "failed", "workflow")
        assert sm.is_terminal_state("failed", "workflow")

    def test_cancelled_workflow_path(self, sm):
        """Test cancelled workflow: PENDING → CANCELLED"""
        sm.validate_transition("pending", "cancelled", "workflow")
        assert sm.is_terminal_state("cancelled", "workflow")

    def test_timeout_workflow_path(self, sm):
        """Test timeout workflow: PENDING → RUNNING → TIMEOUT"""
        sm.validate_transition("pending", "running", "workflow")
        sm.validate_transition("running", "timeout", "workflow")
        assert sm.is_terminal_state("timeout", "workflow")


class TestCompleteTaskLifecycles:
    """Test complete task execution paths"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_successful_task_path(self, sm):
        """Test successful task: PENDING → RUNNING → SUCCEEDED"""
        sm.validate_transition("pending", "running", "task")
        sm.validate_transition("running", "succeeded", "task")
        assert sm.is_terminal_state("succeeded", "task")

    def test_task_with_single_retry(self, sm):
        """Test task with retry: PENDING → RUNNING → RETRYING → RUNNING → SUCCEEDED"""
        sm.validate_transition("pending", "running", "task")
        sm.validate_transition("running", "retrying", "task")
        sm.validate_transition("retrying", "running", "task")
        sm.validate_transition("running", "succeeded", "task")
        assert sm.is_terminal_state("succeeded", "task")

    def test_task_retry_from_failure(self, sm):
        """Test task failure retry: RUNNING → FAILED → RETRYING → RUNNING → SUCCEEDED"""
        sm.validate_transition("running", "failed", "task")
        sm.validate_transition("failed", "retrying", "task")
        sm.validate_transition("retrying", "running", "task")
        sm.validate_transition("running", "succeeded", "task")

    def test_task_exhausted_retries(self, sm):
        """Test task exhausts retries: RUNNING → RETRYING → FAILED"""
        sm.validate_transition("running", "retrying", "task")
        sm.validate_transition("retrying", "failed", "task")
        # After retrying fails, it can still retry again (failed has retrying as allowed)
        assert not sm.is_terminal_state("failed", "task")
        # But timeout is terminal
        sm.validate_transition("retrying", "timeout", "task")
        assert sm.is_terminal_state("timeout", "task")

    def test_task_skipped_path(self, sm):
        """Test skipped task: PENDING → SKIPPED"""
        sm.validate_transition("pending", "skipped", "task")
        assert sm.is_terminal_state("skipped", "task")


class TestEdgeCasesAndBoundaries:
    """Test edge cases and boundary conditions"""

    @pytest.fixture
    def sm(self):
        return WorkflowStateMachine()

    def test_self_transitions_not_allowed(self, sm):
        """Test that states cannot transition to themselves"""
        assert sm.can_transition("pending", "pending", "workflow") is False
        assert sm.can_transition("running", "running", "task") is False
        assert sm.can_transition("succeeded", "succeeded", "workflow") is False

    def test_unknown_entity_type_defaults(self, sm):
        """Test unknown entity_type defaults to task transitions"""
        # SKIPPED is only valid for tasks, not workflows
        result = sm.can_transition("pending", "skipped", "unknown_type")
        # If unknown defaults to task, this should be True
        assert result is True

    def test_empty_string_status(self, sm):
        """Test empty string status"""
        assert sm.can_transition("", "running", "workflow") is False
        assert sm.get_allowed_transitions("", "workflow") == []
        assert sm.is_terminal_state("", "workflow") is True

    def test_none_string_status(self, sm):
        """Test 'none' string status"""
        assert sm.can_transition("none", "running", "workflow") is False
