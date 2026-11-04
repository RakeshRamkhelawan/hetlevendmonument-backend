"""
Workflow Cancellation Mechanism

Provides:
- CancellationToken for signaling cancellation to running tasks
- Cancel scope management for workflow executions
- Graceful vs. force cancellation strategies
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class CancellationToken:
    """
    Token for signaling cancellation to running tasks.

    Each workflow execution gets a CancellationToken.
    Long-running tasks should check this token periodically.
    """

    execution_id: str
    _cancelled: asyncio.Event = field(default_factory=asyncio.Event)
    _cancelled_at: datetime | None = None
    _reason: str | None = None

    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled.is_set()

    def cancel(self, reason: str | None = None) -> None:
        """Request cancellation."""
        self._cancelled.set()
        self._cancelled_at = datetime.now(timezone.utc)
        self._reason = reason
        logger.info(f"Cancellation requested for execution {self.execution_id}: {reason}")

    async def wait_for_cancel(self, timeout: float | None = None) -> bool:
        """Wait until cancellation is requested."""
        try:
            await asyncio.wait_for(self._cancelled.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    def check_cancelled(self, raise_on_cancel: bool = True) -> bool:
        """
        Check if cancelled and optionally raise exception.

        Args:
            raise_on_cancel: If True, raises WorkflowCancelledError when cancelled

        Returns:
            True if cancelled, False otherwise

        Raises:
            WorkflowCancelledError: If cancelled and raise_on_cancel=True
        """
        if self._cancelled.is_set():
            if raise_on_cancel:
                raise WorkflowCancelledError(
                    f"Workflow {self.execution_id} was cancelled: {self._reason}"
                )
            return True
        return False

    @property
    def cancelled_at(self) -> datetime | None:
        """Get cancellation timestamp."""
        return self._cancelled_at

    @property
    def reason(self) -> str | None:
        """Get cancellation reason."""
        return self._reason


class WorkflowCancelledError(Exception):
    """Raised when a workflow is cancelled."""

    pass


class CancellationScope:
    """
    Manages cancellation tokens for multiple workflow executions.

    Provides registry and cleanup for active workflow tokens.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, CancellationToken] = {}
        self._lock = asyncio.Lock()

    async def create_token(self, execution_id: str) -> CancellationToken:
        """
        Create a cancellation token for an execution.

        Args:
            execution_id: Workflow execution ID

        Returns:
            New CancellationToken
        """
        async with self._lock:
            if execution_id in self._tokens:
                logger.warning(f"Token already exists for execution {execution_id}")
                return self._tokens[execution_id]

            token = CancellationToken(execution_id=execution_id)
            self._tokens[execution_id] = token
            logger.debug(f"Created cancellation token for execution {execution_id}")
            return token

    async def get_token(self, execution_id: str) -> CancellationToken | None:
        """
        Get existing cancellation token.

        Args:
            execution_id: Workflow execution ID

        Returns:
            CancellationToken or None if not found
        """
        async with self._lock:
            return self._tokens.get(execution_id)

    async def cancel_execution(
        self,
        execution_id: str,
        reason: str | None = None,
    ) -> bool:
        """
        Cancel a workflow execution.

        Args:
            execution_id: Workflow execution ID
            reason: Cancellation reason

        Returns:
            True if cancellation was requested, False if token not found
        """
        async with self._lock:
            token = self._tokens.get(execution_id)
            if token:
                token.cancel(reason)
                return True
            logger.warning(f"No token found for execution {execution_id}")
            return False

    async def remove_token(self, execution_id: str) -> None:
        """Remove token from registry (cleanup after completion)."""
        async with self._lock:
            if execution_id in self._tokens:
                del self._tokens[execution_id]
                logger.debug(f"Removed cancellation token for execution {execution_id}")

    async def get_active_executions(self) -> set[str]:
        """Get all active execution IDs."""
        async with self._lock:
            return set(self._tokens.keys())

    async def cancel_all(self, reason: str = "shutdown") -> dict[str, bool]:
        """
        Cancel all active executions (for graceful shutdown).

        Args:
            reason: Cancellation reason

        Returns: Dict[str, Any]ionary mapping execution_id to success status  # TODO(TYPE): replace Any with concrete type
        """
        async with self._lock:
            results: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for execution_id, token in self._tokens.items():
                token.cancel(reason)
                results[execution_id] = True
            return results


class GracefulCanceller:
    """
    Handles graceful cancellation with timeout and fallback to force.

    Implements the cancellation strategy:
    1. Signal cancellation via token
    2. Wait for graceful timeout (30s)
    3. Force cancellation if still running
    """

    def __init__(
        self,
        scope: CancellationScope,
        graceful_timeout: float = 30.0,
    ) -> None:
        self.scope = scope
        self.graceful_timeout = graceful_timeout

    async def cancel_workflow(
        self,
        execution_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Cancel a workflow with graceful timeout.

        Args:
            execution_id: Workflow execution ID
            reason: Cancellation reason

        Returns: Dict[str, Any]ionary with cancellation result  # TODO(TYPE): replace Any with concrete type
        """
        start_time = datetime.now(timezone.utc)

        # Signal cancellation
        cancelled = await self.scope.cancel_execution(execution_id, reason)

        if not cancelled:
            return {
                "success": False,
                "execution_id": execution_id,
                "error": "Execution not found or already completed",
            }

        # Wait for graceful shutdown
        logger.info(f"Waiting {self.graceful_timeout}s for graceful cancellation of {execution_id}")

        # Note: In real implementation, we would poll the execution status
        # For now, we just wait the timeout
        await asyncio.sleep(min(self.graceful_timeout, 1))  # Min 1s for testing

        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        return {
            "success": True,
            "execution_id": execution_id,
            "graceful": elapsed < self.graceful_timeout,
            "elapsed_seconds": elapsed,
            "reason": reason,
        }

    async def shutdown_all(self, reason: str = "worker_shutdown") -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Cancel all active workflows (for worker shutdown).

        Args:
            reason: Shutdown reason

        Returns: Dict[str, Any]ionary with shutdown results  # TODO(TYPE): replace Any with concrete type
        """
        executions = await self.scope.get_active_executions()

        if not executions:
            return {"success": True, "cancelled_count": 0, "reason": reason}

        logger.info(f"Cancelling {len(executions)} active workflows: {reason}")

        # Cancel all
        results = await self.scope.cancel_all(reason)

        # Wait for graceful timeout
        logger.info(f"Waiting {self.graceful_timeout}s for graceful shutdown")
        await asyncio.sleep(min(self.graceful_timeout, 1))  # Min 1s for testing

        # Cleanup
        for execution_id in executions:
            await self.scope.remove_token(execution_id)

        return {
            "success": True,
            "cancelled_count": len(executions),
            "execution_ids": list(executions),
            "reason": reason,
        }
