import asyncio

import pytest

from src.core.engine.orchestrator import (
    EngineOrchestrator,
    EngineOrchestratorConfig,
    create_engine_orchestrator,
)


class FailingEngine:
    def __init__(self, calls: list, fail_times: int = 1):
        self.calls = calls
        self._fail_times = fail_times

    async def execute_workflow(self, execution_id: str):
        self.calls.append(execution_id)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("Simulated failure")
        return {"status": "ok", "execution_id": execution_id}


@pytest.mark.asyncio
async def test_orchestrator_routes_to_async_worker():
    calls = []

    def engine_factory(_session=None):
        return FailingEngine(calls, fail_times=0)

    orchestrator = create_engine_orchestrator(engine_factory)
    await orchestrator.start()

    await orchestrator.route_workflow("exec-1", mode="async")

    # wait a short moment to allow async worker to process
    await asyncio.sleep(0.05)

    await orchestrator.stop()

    assert "exec-1" in calls


@pytest.mark.asyncio
async def test_orchestrator_retries_and_dlq():
    """Test that orchestrator sends to DLQ after max retries in realtime mode.

    Note: Retry logic only works in 'realtime' mode where submit() raises exceptions.
    In 'async' mode, exceptions are caught in the background worker loop and not propagated.
    """
    calls = []

    # CRITICAL: Create engine ONCE and reuse it - otherwise each retry gets fresh fail_times
    shared_engine = FailingEngine(calls, fail_times=2)

    def engine_factory(_session=None):
        # Return the SAME engine instance so fail_times state is shared
        return shared_engine

    config = EngineOrchestratorConfig(max_retries=1, retry_delay_seconds=0.01)
    orchestrator = EngineOrchestrator(engine_factory, config=config)
    await orchestrator.start()

    # Use 'realtime' mode - submit() raises exceptions directly
    await orchestrator.route_workflow("exec-dlq", mode="realtime")

    await orchestrator.stop()

    status = orchestrator.get_status()
    assert status["dlq_count"] == 1
    assert "exec-dlq" in calls


@pytest.mark.asyncio
async def test_orchestrator_retries_until_success():
    """Test that orchestrator retries and eventually succeeds in realtime mode.

    Note: Retry logic only works in 'realtime' mode where submit() raises exceptions.
    In 'async' mode, exceptions are caught in the background worker loop and not propagated.
    """
    calls = []

    # CRITICAL: Create engine ONCE and reuse it - otherwise each retry gets fresh fail_times
    shared_engine = FailingEngine(calls, fail_times=1)

    def engine_factory(_session=None):
        # Return the SAME engine instance so fail_times state is shared
        return shared_engine

    config = EngineOrchestratorConfig(max_retries=2, retry_delay_seconds=0.01)
    orchestrator = EngineOrchestrator(engine_factory, config=config)
    await orchestrator.start()

    # Use 'realtime' mode - submit() raises exceptions directly
    await orchestrator.route_workflow("exec-retry", mode="realtime")

    await orchestrator.stop()

    status = orchestrator.get_status()
    assert status["dlq_count"] == 0
    assert calls.count("exec-retry") >= 2
