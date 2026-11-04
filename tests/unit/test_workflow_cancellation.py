"""
Unit tests for Workflow Cancellation

Tests:
- CancellationToken signaling
- CancellationScope management
- Graceful cancellation with timeout
- Force cancellation fallback
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.workflow.cancellation import (
    CancellationScope,
    CancellationToken,
    GracefulCanceller,
    WorkflowCancelledError,
)


class TestCancellationToken:
    """Tests for CancellationToken."""

    def test_token_initial_state(self):
        """Test initial token state."""
        token = CancellationToken(execution_id="exec-123")

        assert token.execution_id == "exec-123"
        assert token.is_cancelled() is False
        assert token.cancelled_at is None
        assert token.reason is None

    def test_token_cancel(self):
        """Test cancellation."""
        token = CancellationToken(execution_id="exec-123")

        token.cancel(reason="User requested")

        assert token.is_cancelled() is True
        assert token.cancelled_at is not None
        assert token.reason == "User requested"

    @pytest.mark.asyncio
    async def test_token_wait_for_cancel(self):
        """Test waiting for cancellation."""
        token = CancellationToken(execution_id="exec-123")

        # Start a task that will cancel after 0.1s
        async def cancel_after_delay():
            await asyncio.sleep(0.1)
            token.cancel()

        # Should not be cancelled yet
        assert token.is_cancelled() is False

        # Start the canceller
        asyncio.create_task(cancel_after_delay())

        # Wait for cancellation (should return True)
        result = await token.wait_for_cancel(timeout=1.0)

        assert result is True
        assert token.is_cancelled() is True

    @pytest.mark.asyncio
    async def test_token_wait_timeout(self):
        """Test wait timeout."""
        token = CancellationToken(execution_id="exec-123")

        # Wait with short timeout (should timeout)
        result = await token.wait_for_cancel(timeout=0.01)

        assert result is False
        assert token.is_cancelled() is False

    def test_token_check_cancelled_raises(self):
        """Test check_cancelled raises exception."""
        token = CancellationToken(execution_id="exec-123")
        token.cancel(reason="Test")

        with pytest.raises(WorkflowCancelledError, match="was cancelled"):
            token.check_cancelled(raise_on_cancel=True)

    def test_token_check_cancelled_no_raise(self):
        """Test check_cancelled returns boolean."""
        token = CancellationToken(execution_id="exec-123")

        # Not cancelled
        result = token.check_cancelled(raise_on_cancel=False)
        assert result is False

        # Cancel
        token.cancel()

        result = token.check_cancelled(raise_on_cancel=False)
        assert result is True


class TestCancellationScope:
    """Tests for CancellationScope."""

    @pytest.fixture
    def scope(self):
        return CancellationScope()

    @pytest.mark.asyncio
    async def test_create_token(self, scope):
        """Test creating a token."""
        token = await scope.create_token("exec-123")

        assert token.execution_id == "exec-123"
        assert await scope.get_token("exec-123") is token

    @pytest.mark.asyncio
    async def test_create_duplicate_token_returns_existing(self, scope):
        """Test creating duplicate token returns existing."""
        token1 = await scope.create_token("exec-123")
        token2 = await scope.create_token("exec-123")

        assert token1 is token2

    @pytest.mark.asyncio
    async def test_get_nonexistent_token(self, scope):
        """Test getting token that doesn't exist."""
        token = await scope.get_token("nonexistent")

        assert token is None

    @pytest.mark.asyncio
    async def test_cancel_execution(self, scope):
        """Test cancelling an execution."""
        await scope.create_token("exec-123")

        result = await scope.cancel_execution("exec-123", reason="Test")

        assert result is True

        token = await scope.get_token("exec-123")
        assert token.is_cancelled() is True
        assert token.reason == "Test"

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_execution(self, scope):
        """Test cancelling nonexistent execution."""
        result = await scope.cancel_execution("nonexistent", reason="Test")

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_token(self, scope):
        """Test removing a token."""
        await scope.create_token("exec-123")
        assert await scope.get_token("exec-123") is not None

        await scope.remove_token("exec-123")

        assert await scope.get_token("exec-123") is None

    @pytest.mark.asyncio
    async def test_get_active_executions(self, scope):
        """Test getting active executions."""
        await scope.create_token("exec-1")
        await scope.create_token("exec-2")
        await scope.create_token("exec-3")

        executions = await scope.get_active_executions()

        assert len(executions) == 3
        assert "exec-1" in executions
        assert "exec-2" in executions
        assert "exec-3" in executions

    @pytest.mark.asyncio
    async def test_cancel_all(self, scope):
        """Test cancelling all executions."""
        await scope.create_token("exec-1")
        await scope.create_token("exec-2")

        results = await scope.cancel_all(reason="shutdown")

        assert len(results) == 2
        assert results["exec-1"] is True
        assert results["exec-2"] is True

        token1 = await scope.get_token("exec-1")
        token2 = await scope.get_token("exec-2")
        assert token1.is_cancelled() is True
        assert token2.is_cancelled() is True


class TestGracefulCanceller:
    """Tests for GracefulCanceller."""

    @pytest.fixture
    def scope(self):
        return CancellationScope()

    @pytest.fixture
    def canceller(self, scope):
        return GracefulCanceller(scope, graceful_timeout=0.1)

    @pytest.mark.asyncio
    async def test_cancel_workflow_success(self, canceller, scope):
        """Test successful workflow cancellation."""
        await scope.create_token("exec-123")

        result = await canceller.cancel_workflow("exec-123", reason="Test")

        assert result["success"] is True
        assert result["execution_id"] == "exec-123"
        assert result["reason"] == "Test"
        assert "elapsed_seconds" in result

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_workflow(self, canceller, scope):
        """Test cancelling nonexistent workflow."""
        result = await canceller.cancel_workflow("nonexistent", reason="Test")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_shutdown_all(self, canceller, scope):
        """Test shutting down all workflows."""
        await scope.create_token("exec-1")
        await scope.create_token("exec-2")

        result = await canceller.shutdown_all(reason="worker_shutdown")

        assert result["success"] is True
        assert result["cancelled_count"] == 2
        assert "exec-1" in result["execution_ids"]
        assert "exec-2" in result["execution_ids"]

    @pytest.mark.asyncio
    async def test_shutdown_all_empty(self, canceller, scope):
        """Test shutting down with no active workflows."""
        result = await canceller.shutdown_all(reason="worker_shutdown")

        assert result["success"] is True
        assert result["cancelled_count"] == 0


class TestWorkflowCancelledError:
    """Tests for WorkflowCancelledError."""

    def test_error_message(self):
        """Test error message format."""
        error = WorkflowCancelledError("exec-123 was cancelled: User request")

        assert "exec-123" in str(error)
        assert "cancelled" in str(error).lower()
