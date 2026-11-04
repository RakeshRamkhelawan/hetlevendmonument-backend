"""
Engine Orchestrator
===================

Minimal orchestrator for routing workflow and task execution to the
worker layer (Async/Batch/Realtime). Includes retry logic and a small
dead-letter queue (DLQ) to capture permanently failing tasks.

This module is intentionally small to be unit-testable and to provide a
clear integration point with `src.core.engine.worker_manager`.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional
from collections.abc import Callable

from src.core.engine.worker_manager import WorkerBase, create_worker

logger = logging.getLogger(__name__)


@dataclass
class EngineOrchestratorConfig:
    max_retries: int = 3
    retry_delay_seconds: float = 0.05  # Small default for fast tests


class EngineOrchestrator:
    """Simple engine-level orchestrator.

    Responsibilities:
    - Route workflow executions to registered workers
    - Basic retry on error with dead-letter queue fallback
    - Provide a small health/status surface
    """

    def __init__(
        self,
        engine_factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        config: EngineOrchestratorConfig | None = None,
    ) -> None:
        self.engine_factory = engine_factory
        self.config = config or EngineOrchestratorConfig()
        # Create default workers
        self.workers: dict[str, WorkerBase] = {
            "async": create_worker("async", engine_factory),
            "batch": create_worker("batch", engine_factory),
            "realtime": create_worker("realtime", engine_factory),
        }
        self._retries: dict[str, int] = {}
        self._dlq: set[str] = set()

    async def start(self) -> None:
        """Start all registered workers."""
        for w in self.workers.values():
            await w.start()
        logger.info("EngineOrchestrator started workers")

    async def stop(self) -> None:
        """Stop all registered workers."""
        for w in self.workers.values():
            await w.stop()
        logger.info("EngineOrchestrator stopped workers")

    async def route_workflow(self, execution_id: str, mode: str = "async") -> None:
        """Route a workflow execution to the chosen worker and handle retries.

        Args:
            execution_id: Workflow identifier
            mode: 'async'|'batch'|'realtime'
        """
        if execution_id in self._dlq:
            logger.warning(f"Execution {execution_id} already in DLQ; ignore")
            return

        worker = self.workers.get(mode)
        if not worker:
            raise ValueError(f"Unknown worker mode: {mode}")

        try:
            logger.debug(f"Routing {execution_id} to worker mode={mode}")
            await worker.submit(execution_id)
            # Success resets retry counter
            self._retries.pop(execution_id, None)
            logger.info(f"Execution {execution_id} dispatched to worker {mode}")
        except Exception as e:  # pragma: no cover - tests cover through fake worker
            logger.error(f"Worker failed to process {execution_id}: {e}")
            await self._handle_worker_failure(execution_id, mode)

    async def _handle_worker_failure(self, execution_id: str, mode: str) -> None:
        # Increment retry count
        self._retries[execution_id] = self._retries.get(execution_id, 0) + 1
        count = self._retries[execution_id]
        logger.warning(f"Retrying {execution_id}: attempt {count}/{self.config.max_retries}")
        if count > self.config.max_retries:
            # move to DLQ
            self._dlq.add(execution_id)
            logger.error(f"Execution {execution_id} sent to DLQ after {count - 1} retries")
            return

        # Wait before retrying (non-blocking)
        await asyncio.sleep(self.config.retry_delay_seconds)
        # Re-route
        await self.route_workflow(execution_id, mode=mode)

    def get_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return status metrics for orchestrator"""
        return {
            "workers": list(self.workers.keys()),
            "queued_retries": dict(self._retries),
            "dlq_count": len(self._dlq),
        }


def create_engine_orchestrator(
    engine_factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
) -> EngineOrchestrator:
    return EngineOrchestrator(engine_factory)
