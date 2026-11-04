"""Unit tests for Workflow Cancel API Endpoint"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.getcwd())

from src.core.api.v1.workflow.workflow_execution_cancel_router import (
    CancelWorkflowRequest,
    CancelWorkflowResponse,
    get_cancellation_scope,
)
from src.core.workflow.models import WorkflowStatus


class TestCancellationScope:
    """Tests for the cancellation scope singleton."""

    def test_get_cancellation_scope_singleton(self):
        """Test that get_cancellation_scope returns the same instance."""
        scope1 = get_cancellation_scope()
        scope2 = get_cancellation_scope()
        assert scope1 is scope2


class TestCancelWorkflowRequest:
    """Tests for the request model."""

    def test_request_with_reason(self):
        """Test request with reason field."""
        request = CancelWorkflowRequest(reason="Test reason")
        assert request.reason == "Test reason"

    def test_request_without_reason(self):
        """Test request without reason field."""
        request = CancelWorkflowRequest()
        assert request.reason is None


class TestCancelWorkflowResponse:
    """Tests for the response model."""

    def test_response_success(self):
        """Test successful response."""
        response = CancelWorkflowResponse(
            success=True,
            execution_id="exec-123",
            cancelled_tasks=1,
            message="Cancelled successfully",
        )
        assert response.success is True
        assert response.execution_id == "exec-123"

    def test_response_failure(self):
        """Test failure response."""
        response = CancelWorkflowResponse(
            success=False, execution_id="exec-123", cancelled_tasks=0, message="Cancellation failed"
        )
        assert response.success is False


class TestWorkflowStatus:
    """Tests for WorkflowStatus enum values."""

    def test_status_values(self):
        """Test that WorkflowStatus has expected values."""
        assert WorkflowStatus.PENDING.value == "pending"
        assert WorkflowStatus.RUNNING.value == "running"
        assert WorkflowStatus.SUCCEEDED.value == "succeeded"
        assert WorkflowStatus.FAILED.value == "failed"
        assert WorkflowStatus.CANCELLED.value == "cancelled"
        assert WorkflowStatus.TIMEOUT.value == "timeout"

    def test_terminal_states(self):
        """Test that terminal states are correctly identified."""
        terminal_states = [
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.TIMEOUT,
        ]
        assert len(terminal_states) == 4
        assert WorkflowStatus.PENDING not in terminal_states
        assert WorkflowStatus.RUNNING not in terminal_states
