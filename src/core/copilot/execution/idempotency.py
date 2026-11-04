"""
ExecutionGuard - Idempotency and locking for Co-Pilot action execution.

Ensures that a CouncilDecision is executed exactly once via the ToolBroker.
Prevents "double charge" or duplicate notifications from retries.

Uses Redis for atomic locking and state tracking.
"""

from __future__ import annotations

import logging
from enum import Enum
from uuid import UUID

from redis.asyncio import Redis

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Execution states for a Council decision."""

    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"


class ExecutionGuard:
    """Guards against duplicate execution of Co-Pilot decisions.

    Key format: copilot:exec:{decision_id}
    """

    def __init__(self, redis: Redis, lock_ttl_seconds: int = 60) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._ttl = lock_ttl_seconds

    def _key(self, decision_id: UUID) -> str:
        return f"copilot:exec:{decision_id}"

    async def start_execution(self, decision_id: UUID) -> bool:
        """Attempt to acquire an execution lock for a decision.

        Returns:
            True if the lock was acquired and execution can proceed.
            False if the action is already being processed or finished.
        """
        key = self._key(decision_id)
        # SET decision_id "PROCESSING" EX 60 NX
        # NX = Only set if NOT exists (atomic lock)
        success = await self._redis.set(
            key, ExecutionStatus.PROCESSING.value, ex=self._ttl, nx=True
        )
        if not success:
            # Check current status
            status = await self._redis.get(key)
            logger.warning(
                "execution_guard.blocked decision_id=%s current_status=%s",
                decision_id,
                status,
            )
            return False

        logger.debug("execution_guard.lock_acquired decision_id=%s", decision_id)
        return True

    async def finish_execution(self, decision_id: UUID, status: ExecutionStatus) -> None:
        """Update the final status of an execution.

        If SUCCESS, the lock is kept (or extended) to prevent re-runs.
        If FAILED, the lock is released (or marked as FAILED) to allow retry.
        """
        if status not in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED):
            raise ValueError(f"Invalid terminal status: {status}")

        key = self._key(decision_id)
        # Keep SUCCESS for a long time (1 hour) to prevent any accidental re-runs
        ttl = 3600 if status == ExecutionStatus.SUCCESS else 60

        await self._redis.set(key, status.value, ex=ttl)
        logger.info(
            "execution_guard.finished decision_id=%s status=%s",
            decision_id,
            status,
        )

    async def get_status(self, decision_id: UUID) -> ExecutionStatus | None:
        """Check the current execution status of a decision."""
        key = self._key(decision_id)
        val = await self._redis.get(key)
        if val is None:
            return None
        try:
            return ExecutionStatus(val.decode("utf-8") if isinstance(val, bytes) else val)
        except ValueError:
            return None
