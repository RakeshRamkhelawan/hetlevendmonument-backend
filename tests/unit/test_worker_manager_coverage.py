import asyncio

import pytest

from src.core.engine.worker_manager import (
    AsyncWorker,
    BatchWorker,
    RealtimeWorker,
    WorkerConfig,
    create_worker,
)


class FakeEngine:
    def __init__(self, record_list: list):
        self.record_list = record_list

    async def execute_workflow(self, execution_id: str):
        # Simulate processing
        await asyncio.sleep(0.01)
        self.record_list.append(execution_id)
        return {"status": "ok", "execution_id": execution_id}


# The test suite uses pytest.mark.asyncio for coroutine tests


@pytest.mark.asyncio
async def test_async_worker_processes_jobs():
    calls: list = []

    def engine_factory(_session=None):
        return FakeEngine(calls)

    worker = AsyncWorker(engine_factory)
    await worker.start()

    await worker.submit("job-1")
    await worker.submit("job-2")

    # Give it some time to process
    await asyncio.sleep(0.05)

    await worker.stop()

    assert "job-1" in calls and "job-2" in calls


@pytest.mark.asyncio
async def test_batch_worker_batches_tasks():
    calls: list = []

    def engine_factory(_session=None):
        return FakeEngine(calls)

    config = WorkerConfig(batch_size=2, batch_interval_seconds=1)
    worker = BatchWorker(engine_factory, config)
    await worker.start()

    await worker.submit("b-job-1")
    # At this point the batch shouldn't be processed yet
    assert len(calls) == 0

    await worker.submit("b-job-2")
    # Wait a bit for batch to be processed
    await asyncio.sleep(0.1)

    await worker.stop()

    assert "b-job-1" in calls and "b-job-2" in calls


@pytest.mark.asyncio
async def test_realtime_worker_returns_result():
    calls: list = []

    class FastEngine:
        async def execute_workflow(self, execution_id: str):
            return {"status": "ok", "execution_id": execution_id}

    def engine_factory(_session=None):
        return FastEngine()

    worker = RealtimeWorker(engine_factory)
    await worker.start()

    result = await worker.submit("rt-job-1")

    await worker.stop()

    assert result["execution_id"] == "rt-job-1"
    assert result["status"] == "ok"


@pytest.mark.parametrize("mode", ["async", "batch", "realtime"])
def test_create_worker_factory(mode):
    w = create_worker(mode, lambda _: None)
    assert w is not None
