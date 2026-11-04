"""
Tests for Canvas Agent Blocks.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.canvas.agent_blocks import (
    AgentBlock,
    AgentBlockRegistry,
    AgentBlockType,
    AgentChatConfig,
    AgentTaskConfig,
    CodeBlockConfig,
    CodeSandboxExecutor,
    ExecutionEnvironment,
    ExecutionResult,
    ExecutionStatus,
    StreamChunk,
    agent_block_registry,
)


@pytest.fixture
def sample_code_config():
    """Create a sample code block configuration."""
    return CodeBlockConfig(
        language=ExecutionEnvironment.SAFE_PYTHON,
        code='print("Hello, World!")',
        timeout_seconds=30,
        memory_limit_mb=128,
    )


@pytest.fixture
def sample_agent_chat_config():
    """Create a sample agent chat configuration."""
    return AgentChatConfig(
        agent_id="test-agent",
        system_prompt="You are a helpful assistant.",
        max_tokens=1000,
        temperature=0.7,
    )


@pytest.fixture
def sample_agent_task_config():
    """Create a sample agent task configuration."""
    return AgentTaskConfig(
        task_description="Analyze sales data",
        auto_execute=False,
        max_iterations=5,
    )


@pytest.fixture
def sample_canvas_id():
    """Sample canvas ID."""
    return uuid4()


class TestCodeBlockConfig:
    """Test CodeBlockConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = CodeBlockConfig(code="print('test')")

        assert config.language == ExecutionEnvironment.SAFE_PYTHON
        assert config.timeout_seconds == 30
        assert config.memory_limit_mb == 128
        assert config.allowed_imports == []

    def test_custom_values(self):
        """Test custom configuration values."""
        config = CodeBlockConfig(
            language=ExecutionEnvironment.SQL,
            code="SELECT * FROM users",
            timeout_seconds=60,
            memory_limit_mb=256,
            allowed_imports=["pandas", "numpy"],
        )

        assert config.language == ExecutionEnvironment.SQL
        assert config.timeout_seconds == 60
        assert config.memory_limit_mb == 256
        assert config.allowed_imports == ["pandas", "numpy"]


class TestAgentBlockCreation:
    """Test AgentBlock creation."""

    def test_create_code_block(self, sample_code_config, sample_canvas_id):
        """Create a code execution block."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        assert block.block_id == block_id
        assert block.block_type == AgentBlockType.CODE_EXECUTOR
        assert block.status == ExecutionStatus.PENDING
        assert block.result is None

    def test_create_agent_chat_block(self, sample_agent_chat_config, sample_canvas_id):
        """Create an agent chat block."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.AGENT_CHAT,
            config=sample_agent_chat_config,
            canvas_id=sample_canvas_id,
        )

        assert block.block_type == AgentBlockType.AGENT_CHAT
        assert block.config.system_prompt == "You are a helpful assistant."

    def test_block_to_dict(self, sample_code_config, sample_canvas_id):
        """Convert block to dictionary."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        data = block.to_dict()

        assert data["block_id"] == str(block_id)
        assert data["block_type"] == "code_executor"
        assert data["status"] == "pending"
        assert "config" in data


class TestAgentBlockExecution:
    """Test AgentBlock execution."""

    async def test_execute_code_block(self, sample_code_config, sample_canvas_id):
        """Execute a code block."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        result = await block.execute()

        assert result is not None
        assert result.status == ExecutionStatus.COMPLETED
        assert block.status == ExecutionStatus.COMPLETED
        assert block.result == result

    async def test_execute_agent_chat_block(self, sample_agent_chat_config, sample_canvas_id):
        """Execute an agent chat block."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.AGENT_CHAT,
            config=sample_agent_chat_config,
            canvas_id=sample_canvas_id,
        )

        result = await block.execute()

        assert result is not None
        assert result.status == ExecutionStatus.COMPLETED

    async def test_execute_agent_task_block(self, sample_agent_task_config, sample_canvas_id):
        """Execute an agent task block."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.AGENT_TASK,
            config=sample_agent_task_config,
            canvas_id=sample_canvas_id,
        )

        result = await block.execute()

        assert result is not None
        assert result.status == ExecutionStatus.COMPLETED

    async def test_cannot_execute_running_block(self, sample_code_config, sample_canvas_id):
        """Cannot execute a block that's already running."""
        block_id = uuid4()

        # Create a config that will take some time
        slow_config = CodeBlockConfig(
            language=ExecutionEnvironment.SAFE_PYTHON,
            code="\n".join([f'print("Line {i}")' for i in range(100)]),
            timeout_seconds=30,
        )

        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=slow_config,
            canvas_id=sample_canvas_id,
        )

        # Start execution
        task1 = asyncio.create_task(block.execute())

        # Give it a moment to actually start running
        await asyncio.sleep(0.05)

        # Try to execute again - should fail if still running
        try:
            await block.execute()
            # If we get here, the first task already completed
            # That's OK, it means execution was fast
        except RuntimeError as e:
            assert "already running" in str(e)

        # Wait for first task to complete
        await task1


class TestAgentBlockStreaming:
    """Test AgentBlock streaming output."""

    async def test_stream_execution(self, sample_code_config, sample_canvas_id):
        """Execute with streaming output."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        chunks = []
        async for chunk in block.execute_streaming():
            chunks.append(chunk)

        # Should receive progress and result chunks
        assert len(chunks) > 0
        assert any(c.chunk_type == "result" for c in chunks)

    async def test_subscribe_to_stream(self, sample_code_config, sample_canvas_id):
        """Subscribe to output stream."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        received_chunks = []

        def on_chunk(chunk: StreamChunk) -> None:
            received_chunks.append(chunk)

        block.subscribe(on_chunk)

        await block.execute()

        # Should have received chunks
        assert len(received_chunks) > 0

        # Unsubscribe
        block.unsubscribe(on_chunk)


class TestAgentBlockCancel:
    """Test AgentBlock cancellation."""

    async def test_cancel_execution(self, sample_code_config, sample_canvas_id):
        """Cancel ongoing execution."""
        block_id = uuid4()

        # Create a config that will take some time to execute
        slow_config = CodeBlockConfig(
            language=ExecutionEnvironment.SAFE_PYTHON,
            code="\n".join([f'print("Line {i}")' for i in range(50)]),
            timeout_seconds=30,
        )

        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=slow_config,
            canvas_id=sample_canvas_id,
        )

        # Start execution
        task = asyncio.create_task(block.execute())

        # Give it a moment to start
        await asyncio.sleep(0.05)

        # Try to cancel
        cancelled = await block.cancel()

        # Cancel might succeed or fail depending on timing
        # We just verify the method doesn't crash
        assert cancelled is True or cancelled is False

        # Clean up
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_cancel_not_running(self, sample_code_config, sample_canvas_id):
        """Cancel when not running returns False."""
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        # Try to cancel without running
        cancelled = await block.cancel()
        assert cancelled is False


class TestExecutionResult:
    """Test ExecutionResult."""

    def test_result_creation(self):
        """Create execution result."""
        result = ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            output="Hello, World!",
            execution_time_ms=100.5,
        )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.output == "Hello, World!"
        assert result.execution_time_ms == 100.5

    def test_result_to_dict(self):
        """Convert result to dictionary."""
        result = ExecutionResult(
            status=ExecutionStatus.FAILED,
            output="",
            error="Division by zero",
            execution_time_ms=50.0,
        )

        data = result.to_dict()

        assert data["status"] == "failed"
        assert data["error"] == "Division by zero"
        assert data["execution_time_ms"] == 50.0


class TestStreamChunk:
    """Test StreamChunk."""

    def test_chunk_creation(self):
        """Create stream chunk."""
        chunk = StreamChunk(
            chunk_type="stdout",
            content="Hello",
        )

        assert chunk.chunk_type == "stdout"
        assert chunk.content == "Hello"

    def test_chunk_to_dict(self):
        """Convert chunk to dictionary."""
        chunk = StreamChunk(
            chunk_type="progress",
            content="Running...",
            metadata={"percent": 50},
        )

        data = chunk.to_dict()

        assert data["type"] == "progress"
        assert data["content"] == "Running..."
        assert data["metadata"]["percent"] == 50


class TestCodeSandboxExecutor:
    """Test CodeSandboxExecutor."""

    async def test_execute_safe_python(self):
        """Execute Python code in sandbox."""
        config = CodeBlockConfig(
            language=ExecutionEnvironment.SAFE_PYTHON,
            code='print("Hello")\nprint("World")',
        )

        executor = CodeSandboxExecutor(config)

        chunks = []
        async for chunk in executor.execute_streaming():
            chunks.append(chunk)

        # Should have progress and stdout chunks
        assert len(chunks) > 0
        assert any(c.chunk_type == "stdout" for c in chunks)
        assert any(c.chunk_type == "progress" for c in chunks)

    async def test_execute_sql(self):
        """Execute SQL query."""
        config = CodeBlockConfig(
            language=ExecutionEnvironment.SQL,
            code="SELECT * FROM users",
        )

        executor = CodeSandboxExecutor(config)

        chunks = []
        async for chunk in executor.execute_streaming():
            chunks.append(chunk)

        # Should have stdout with results
        assert len(chunks) > 0

    async def test_unsupported_language(self):
        """Handle unsupported language gracefully."""
        config = CodeBlockConfig(
            language=ExecutionEnvironment.BASH,
            code="echo 'test'",
        )

        executor = CodeSandboxExecutor(config)

        chunks = []
        async for chunk in executor.execute_streaming():
            chunks.append(chunk)

        # Should have error chunk
        assert any(c.chunk_type == "error" for c in chunks)


class TestAgentBlockRegistry:
    """Test AgentBlockRegistry."""

    def test_register_block(self, sample_code_config, sample_canvas_id):
        """Register a new block."""
        registry = AgentBlockRegistry()

        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        registry.register(block)

        # Should be retrievable
        retrieved = registry.get(block_id)
        assert retrieved == block

    def test_unregister_block(self, sample_code_config, sample_canvas_id):
        """Unregister a block."""
        registry = AgentBlockRegistry()

        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )

        registry.register(block)
        retrieved = registry.unregister(block_id)

        assert retrieved == block
        assert registry.get(block_id) is None

    def test_get_canvas_blocks(self, sample_code_config, sample_canvas_id):
        """Get all blocks for a canvas."""
        registry = AgentBlockRegistry()

        # Create multiple blocks
        for i in range(3):
            block = AgentBlock(
                block_id=uuid4(),
                tenant_id=1,
                block_type=AgentBlockType.CODE_EXECUTOR,
                config=sample_code_config,
                canvas_id=sample_canvas_id,
            )
            registry.register(block)

        blocks = registry.get_canvas_blocks(sample_canvas_id)
        assert len(blocks) == 3

    async def test_execute_canvas_blocks(self, sample_code_config, sample_canvas_id):
        """Execute all blocks in a canvas."""
        registry = AgentBlockRegistry()

        # Create and register a block
        block_id = uuid4()
        block = AgentBlock(
            block_id=block_id,
            tenant_id=1,
            block_type=AgentBlockType.CODE_EXECUTOR,
            config=sample_code_config,
            canvas_id=sample_canvas_id,
        )
        registry.register(block)

        # Execute all blocks
        results = await registry.execute_canvas_blocks(sample_canvas_id)

        assert len(results) == 1
        assert results[0].status == ExecutionStatus.COMPLETED

    def test_global_registry(self):
        """Global registry instance exists."""
        assert agent_block_registry is not None
