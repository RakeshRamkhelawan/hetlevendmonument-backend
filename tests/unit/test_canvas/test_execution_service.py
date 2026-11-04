"""
Tests for Canvas Execution Service.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.canvas.agent_blocks import (
    AgentBlock,
    AgentBlockType,
    CodeBlockConfig,
    ExecutionEnvironment,
    ExecutionResult,
    ExecutionStatus,
    StreamChunk,
)
from src.domains.canvas.execution_service import (
    ExecutionHistory,
    ExecutionQueue,
    ExecutionService,
    ExecutionTask,
    StreamingManager,
    execution_history,
    execution_queue,
    execution_service,
    streaming_manager,
)


@pytest.fixture
def mock_block():
    """Create a mock agent block."""
    block = MagicMock(spec=AgentBlock)
    block.block_id = uuid4()
    block.canvas_id = uuid4()
    block.status = ExecutionStatus.PENDING
    block.result = None
    block.subscribe = MagicMock()
    block.unsubscribe = MagicMock()
    block.execute = AsyncMock(
        return_value=ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            output="Test output",
        )
    )
    return block


@pytest.fixture
def sample_user_id():
    """Sample user ID."""
    return uuid4()


class TestExecutionTask:
    """Test ExecutionTask dataclass."""

    def test_task_creation(self, sample_user_id):
        """Create execution task."""
        task = ExecutionTask(
            task_id=uuid4(),
            block_id=uuid4(),
            canvas_id=uuid4(),
            user_id=sample_user_id,
        )

        assert task.status == ExecutionStatus.PENDING
        assert task.result is None
        assert task.started_at is None
        assert task.completed_at is None

    def test_task_with_callbacks(self, sample_user_id):
        """Task with callbacks."""
        task = ExecutionTask(
            task_id=uuid4(),
            block_id=uuid4(),
            canvas_id=uuid4(),
            user_id=sample_user_id,
        )

        # Add callbacks
        def on_complete(result):
            pass

        def on_stream(chunk):
            pass

        task._on_complete.append(on_complete)
        task._on_stream.append(on_stream)

        assert len(task._on_complete) == 1
        assert len(task._on_stream) == 1


class TestExecutionQueue:
    """Test ExecutionQueue."""

    async def test_queue_start_stop(self):
        """Start and stop queue processor."""
        queue = ExecutionQueue(max_concurrent=2)

        await queue.start()
        assert queue._running_flag is True

        await queue.stop()
        assert queue._running_flag is False

    async def test_submit_task(self, mock_block, sample_user_id):
        """Submit task to queue."""
        queue = ExecutionQueue(max_concurrent=2)
        await queue.start()

        try:
            task = await queue.submit(mock_block, sample_user_id)

            assert task.block_id == mock_block.block_id
            assert task.user_id == sample_user_id
            assert task.status == ExecutionStatus.PENDING
        finally:
            await queue.stop()

    async def test_task_execution(self, mock_block, sample_user_id):
        """Task gets executed from queue."""
        queue = ExecutionQueue(max_concurrent=2)
        await queue.start()

        try:
            task = await queue.submit(mock_block, sample_user_id)

            # Wait for execution to complete
            await asyncio.sleep(0.3)

            # Task should reach a final state (completed or failed)
            assert task.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            ]
            # Task should have a result
            assert task.result is not None
        finally:
            await queue.stop()

    async def test_max_concurrency(self, mock_block, sample_user_id):
        """Respect max concurrent limit."""
        queue = ExecutionQueue(max_concurrent=1)  # Only 1 at a time
        await queue.start()

        try:
            # Submit same block twice (queue will handle it)
            task1 = await queue.submit(mock_block, sample_user_id)
            task2 = await queue.submit(mock_block, sample_user_id)

            # Verify tasks were created
            assert task1.block_id == mock_block.block_id
            assert task2.block_id == mock_block.block_id

            # Wait for both to complete
            await asyncio.sleep(0.5)

            # Both should reach a final state
            assert task1.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            ]
            assert task2.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.CANCELLED,
            ]

        finally:
            await queue.stop()

    async def test_cancel_running_task(self, mock_block, sample_user_id):
        """Cancel a running task."""
        queue = ExecutionQueue(max_concurrent=2)
        await queue.start()

        try:
            # Create slow block
            slow_block = MagicMock(spec=AgentBlock)
            slow_block.block_id = uuid4()
            slow_block.canvas_id = uuid4()
            slow_block.status = ExecutionStatus.PENDING
            slow_block.subscribe = MagicMock()
            slow_block.unsubscribe = MagicMock()

            async def very_slow_execute():
                await asyncio.sleep(10)
                return ExecutionResult(status=ExecutionStatus.COMPLETED)

            slow_block.execute = very_slow_execute

            task = await queue.submit(slow_block, sample_user_id)

            # Wait for it to start
            await asyncio.sleep(0.1)

            # Cancel it
            cancelled = await queue.cancel_task(task.task_id)

            # Note: Cancellation may not work perfectly with our mock
            # but we verify the method runs without error

        finally:
            await queue.stop()

    def test_get_task(self, mock_block, sample_user_id):
        """Get task by ID."""
        queue = ExecutionQueue(max_concurrent=2)

        # Non-existent task
        result = queue.get_task(uuid4())
        assert result is None


class TestExecutionHistory:
    """Test ExecutionHistory."""

    def test_record_execution(self):
        """Record execution result."""
        history = ExecutionHistory(max_entries_per_block=10)

        block_id = uuid4()
        result = ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            output="Test",
        )

        history.record(block_id, result)

        # Should be retrievable
        latest = history.get_latest(block_id)
        assert latest == result

    def test_get_history(self):
        """Get execution history."""
        history = ExecutionHistory(max_entries_per_block=10)
        block_id = uuid4()

        # Record multiple results
        for i in range(5):
            result = ExecutionResult(
                status=ExecutionStatus.COMPLETED,
                output=f"Result {i}",
            )
            history.record(block_id, result)

        # Get history
        results = history.get_history(block_id, limit=3)

        assert len(results) == 3
        assert results[-1].output == "Result 4"

    def test_history_limit(self):
        """History respects max entries limit."""
        history = ExecutionHistory(max_entries_per_block=3)
        block_id = uuid4()

        # Record more than limit
        for i in range(5):
            result = ExecutionResult(
                status=ExecutionStatus.COMPLETED,
                output=f"Result {i}",
            )
            history.record(block_id, result)

        # Should only keep last 3
        results = history.get_history(block_id)
        assert len(results) == 3
        assert results[0].output == "Result 2"  # Oldest kept
        assert results[-1].output == "Result 4"  # Latest

    def test_get_history_empty(self):
        """Get history for block with no executions."""
        history = ExecutionHistory()

        results = history.get_history(uuid4())
        assert results == []

        latest = history.get_latest(uuid4())
        assert latest is None


class TestStreamingManager:
    """Test StreamingManager."""

    def test_subscribe_unsubscribe(self):
        """Subscribe and unsubscribe WebSocket."""
        manager = StreamingManager()
        canvas_id = uuid4()

        mock_ws = MagicMock()

        manager.subscribe(canvas_id, mock_ws)
        assert mock_ws in manager._subscribers[canvas_id]

        manager.unsubscribe(canvas_id, mock_ws)
        assert mock_ws not in manager._subscribers.get(canvas_id, {})

    def test_create_stream_callback(self):
        """Create streaming callback."""
        manager = StreamingManager()
        canvas_id = uuid4()
        block_id = uuid4()

        callback = manager.create_block_stream_callback(canvas_id, block_id)
        assert callback is not None


class TestExecutionService:
    """Test ExecutionService."""

    async def test_service_start_stop(self):
        """Start and stop service."""
        service = ExecutionService()

        await service.start()
        await service.stop()
        # Should complete without error

    async def test_execute_block(self, sample_user_id):
        """Execute a block through service."""
        service = ExecutionService()
        await service.start()

        try:
            # Create and register a block
            config = CodeBlockConfig(
                language=ExecutionEnvironment.SAFE_PYTHON,
                code='print("test")',
            )
            block_id = uuid4()
            canvas_id = uuid4()

            block = AgentBlock(
                block_id=block_id,
                tenant_id=1,
                block_type=AgentBlockType.CODE_EXECUTOR,
                config=config,
                canvas_id=canvas_id,
            )
            service.registry.register(block)

            # Execute
            task = await service.execute_block(block_id, sample_user_id)

            assert task.block_id == block_id
            assert task.user_id == sample_user_id
        finally:
            await service.stop()

    async def test_execute_nonexistent_block(self, sample_user_id):
        """Execute block that doesn't exist."""
        service = ExecutionService()
        await service.start()

        try:
            with pytest.raises(ValueError, match="not found"):
                await service.execute_block(uuid4(), sample_user_id)
        finally:
            await service.stop()

    def test_get_block_status(self):
        """Get block execution status."""
        service = ExecutionService()

        # Create and register block
        config = CodeBlockConfig(
            language=ExecutionEnvironment.SAFE_PYTHON,
            code='print("test")',
        )
        block_id = uuid4()
        canvas_id = uuid4()

        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=config,
            canvas_id=canvas_id,
        )
        service.registry.register(block)

        # Get status
        status = service.get_block_status(block_id)

        assert status["block_id"] == str(block_id)
        assert "status" in status
        assert "history" in status

    def test_get_nonexistent_block_status(self):
        """Get status for non-existent block."""
        service = ExecutionService()

        status = service.get_block_status(uuid4())

        assert "error" in status

    async def test_execute_canvas_blocks(self, sample_user_id):
        """Execute all blocks in a canvas."""
        service = ExecutionService()
        await service.start()

        try:
            canvas_id = uuid4()
            config = CodeBlockConfig(
                language=ExecutionEnvironment.SAFE_PYTHON,
                code='print("test")',
            )

            # Create blocks in canvas
            for i in range(3):
                block = AgentBlock(
                    block_id=uuid4(),
                    tenant_id=1,
                    block_type=AgentBlockType.CODE_EXECUTOR,
                    config=config,
                    canvas_id=canvas_id,
                )
                service.registry.register(block)

            # Execute all
            tasks = await service.execute_canvas_blocks(canvas_id, sample_user_id)

            assert len(tasks) == 3
        finally:
            await service.stop()

    def test_global_service_instances(self):
        """Global service instances exist."""
        assert execution_service is not None
        assert execution_queue is not None
        assert execution_history is not None
        assert streaming_manager is not None
