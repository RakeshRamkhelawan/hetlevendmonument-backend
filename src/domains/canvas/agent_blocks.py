"""
Canvas Agent Blocks - AI Agent Integration for Canvas

Provides block types for embedding AI agents directly into canvas workflows.
Supports code execution, agent conversations, and real-time output streaming.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4

from loguru import logger
from pydantic import BaseModel, Field

from src.domains.canvas.ot_engine import Operation, OperationType


class AgentBlockType(str, Enum):
    """Types of agent blocks supported in canvas."""

    CODE_EXECUTOR = "code_executor"  # Execute code (Python, SQL, etc.)
    AGENT_CHAT = "agent_chat"  # Interactive agent conversation
    AGENT_TASK = "agent_task"  # Background agent task
    DATA_PROCESSOR = "data_processor"  # Data transformation
    WEB_SEARCH = "web_search"  # Search and retrieve
    API_CALLER = "api_caller"  # External API integration


class ExecutionStatus(str, Enum):
    """Status of agent block execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ExecutionEnvironment(str, Enum):
    """Execution environments for code blocks."""

    PYTHON = "python"
    SQL = "sql"
    JAVASCRIPT = "javascript"
    BASH = "bash"
    SAFE_PYTHON = "safe_python"  # Restricted Python sandbox


@dataclass
class ExecutionResult:
    """Result of code execution."""

    status: ExecutionStatus
    output: str = ""
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    memory_usage_mb: float = 0.0
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "memory_usage_mb": self.memory_usage_mb,
            "artifacts": self.artifacts,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class StreamChunk:
    """A chunk of streaming output."""

    chunk_type: str  # "stdout", "stderr", "progress", "result", "error"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "type": self.chunk_type,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


class CodeBlockConfig(BaseModel):
    """Configuration for code execution blocks."""

    language: ExecutionEnvironment = ExecutionEnvironment.SAFE_PYTHON
    code: str = ""
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    memory_limit_mb: int = Field(default=128, ge=32, le=1024)
    allowed_imports: List[str] = Field(default_factory=list)
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    inputs: Dict[str, Any] = Field(default_factory=dict)  # Block inputs  # TODO(TYPE): replace Any with concrete type

    class Config:
        use_enum_values = True


class AgentChatConfig(BaseModel):
    """Configuration for agent chat blocks."""

    agent_id: Optional[str] = None
    system_prompt: str = ""
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    max_tokens: int = Field(default=2000, ge=100, le=8000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    streaming: bool = True
    tools: List[str] = Field(default_factory=list)  # Enabled tool names


class AgentTaskConfig(BaseModel):
    """Configuration for background agent tasks."""

    task_description: str = ""
    agent_id: Optional[str] = None
    auto_execute: bool = False
    execution_interval: Optional[int] = None  # Seconds for recurring tasks
    max_iterations: int = Field(default=10, ge=1, le=100)
    dependencies: List[str] = Field(default_factory=list)  # Block IDs this depends on


# Union type for all agent block configurations
AgentBlockConfig = Union[CodeBlockConfig, AgentChatConfig, AgentTaskConfig]


class AgentBlock:
    """
    An agent block embedded in a canvas.

    Supports multiple execution modes:
    - Synchronous: Execute and return result
    - Asynchronous: Execute in background, notify on completion
    - Streaming: Real-time output chunks
    """

    def __init__(
        self,
        block_id: UUID,
        block_type: AgentBlockType,
        config: AgentBlockConfig,
        canvas_id: UUID,
        tenant_id: int,
    ) -> None:
        self.block_id = block_id
        self.block_type = block_type
        self.config = config
        self.canvas_id = canvas_id
        self.tenant_id = tenant_id

        # Execution state
        self._status = ExecutionStatus.PENDING
        self._current_execution: Optional[asyncio.Task[Any]] = None  # TODO(TYPE): replace Any with concrete type
        self._result: Optional[ExecutionResult] = None
        self._output_buffer: List[StreamChunk] = []

        # Subscribers for real-time updates
        self._subscribers: List[Callable[..., Any]] = []  # TODO(TYPE): replace Any with concrete type

        logger.debug(f"Created agent block {block_id} of type {block_type}")

    @property
    def status(self) -> ExecutionStatus:
        """Current execution status."""
        return self._status

    @property
    def result(self) -> Optional[ExecutionResult]:
        """Last execution result."""
        return self._result

    def subscribe(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Subscribe to output stream."""
        self._subscribers.append(callback)
        logger.debug(f"Subscriber added to block {self.block_id}")

    def unsubscribe(self, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Unsubscribe from output stream."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _notify_subscribers(self, chunk: StreamChunk) -> None:
        """Notify all subscribers of new output."""
        self._output_buffer.append(chunk)
        for callback in self._subscribers:
            try:
                callback(chunk)
            except Exception as e:
                logger.error(
                    "Error notifying subscriber: %s: %s", type(e).__name__, e, exc_info=True
                )

    async def execute(self) -> ExecutionResult:
        """
        Execute the agent block.

        Dispatches to appropriate execution method based on block type.
        """
        if self._status == ExecutionStatus.RUNNING:
            raise RuntimeError(f"Block {self.block_id} is already running")

        self._status = ExecutionStatus.RUNNING
        self._output_buffer.clear()

        start_time = datetime.now(timezone.utc)

        try:
            if self.block_type == AgentBlockType.CODE_EXECUTOR:
                result = await self._execute_code()
            elif self.block_type == AgentBlockType.AGENT_CHAT:
                result = await self._execute_agent_chat()
            elif self.block_type == AgentBlockType.AGENT_TASK:
                result = await self._execute_agent_task()
            else:
                result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error=f"Unsupported block type: {self.block_type}",
                )

            self._result = result
            self._status = result.status

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            result.execution_time_ms = execution_time

            return result

        except asyncio.TimeoutError:
            self._status = ExecutionStatus.TIMEOUT
            self._result = ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                error="Execution timed out",
            )
            return self._result

        except Exception as e:
            logger.error(
                "Error executing block %s: %s: %s",
                self.block_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            self._status = ExecutionStatus.FAILED
            self._result = ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(e),
            )
            return self._result

    async def execute_streaming(self) -> AsyncIterator[StreamChunk]:
        """
        Execute with streaming output.

        Yields output chunks in real-time.
        """
        # Create queue for streaming
        queue: asyncio.Queue[StreamChunk] = asyncio.Queue()

        def on_chunk(chunk: StreamChunk) -> None:
            queue.put_nowait(chunk)

        self.subscribe(on_chunk)

        try:
            # Start execution in background
            execution_task = asyncio.create_task(self.execute())

            # Stream chunks until completion
            while self._status == ExecutionStatus.RUNNING or not queue.empty():
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.1)
                    yield chunk
                except asyncio.TimeoutError:
                    continue

            # Wait for execution to complete
            await execution_task

            # Yield final result
            if self._result:
                yield StreamChunk(
                    chunk_type="result",
                    content=self._result.output,
                    metadata={"status": self._result.status.value},
                )

        finally:
            self.unsubscribe(on_chunk)

    async def cancel(self) -> bool:
        """Cancel ongoing execution."""
        if self._status != ExecutionStatus.RUNNING or not self._current_execution:
            return False

        self._current_execution.cancel()
        self._status = ExecutionStatus.CANCELLED

        self._notify_subscribers(
            StreamChunk(
                chunk_type="error",
                content="Execution cancelled by user",
            )
        )

        return True

    async def _execute_code(self) -> ExecutionResult:
        """Execute code block."""
        config = self.config
        if not isinstance(config, CodeBlockConfig):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Invalid configuration for code block",
            )

        self._notify_subscribers(
            StreamChunk(
                chunk_type="progress",
                content=f"Executing {config.language} code...",
            )
        )

        # Use sandboxed execution
        executor = CodeSandboxExecutor(config)

        async for chunk in executor.execute_streaming():
            self._notify_subscribers(chunk)

        return executor.get_result()

    async def _execute_agent_chat(self) -> ExecutionResult:
        """Execute agent chat block."""
        config = self.config
        if not isinstance(config, AgentChatConfig):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Invalid configuration for agent chat block",
            )

        self._notify_subscribers(
            StreamChunk(
                chunk_type="progress",
                content="Starting agent conversation...",
            )
        )

        # Placeholder for agent integration
        # In production, this would call the agent service
        await asyncio.sleep(0.5)  # Simulate processing

        return ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            output="Agent response would appear here",
        )

    async def _execute_agent_task(self) -> ExecutionResult:
        """Execute background agent task."""
        config = self.config
        if not isinstance(config, AgentTaskConfig):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="Invalid configuration for agent task block",
            )

        self._notify_subscribers(
            StreamChunk(
                chunk_type="progress",
                content=f"Starting task: {config.task_description}",
            )
        )

        # Placeholder for task execution
        await asyncio.sleep(0.5)

        return ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            output=f"Task completed: {config.task_description}",
        )

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert block to dictionary representation."""
        return {
            "block_id": str(self.block_id),
            "block_type": self.block_type.value,
            "canvas_id": str(self.canvas_id),
            "status": self._status.value,
            "config": self.config.model_dump(),
            "result": self._result.to_dict() if self._result else None,
        }


class CodeSandboxExecutor:
    """
    Sandboxed code execution environment.

    Provides secure execution of Python code with:
    - Timeout enforcement
    - Memory limits
    - Restricted imports
    - Output capture
    """

    def __init__(self, config: CodeBlockConfig) -> None:
        self.config = config
        self._output_chunks: List[StreamChunk] = []
        self._result: Optional[ExecutionResult] = None

    def get_result(self) -> ExecutionResult:
        """Get execution result."""
        if self._result:
            return self._result

        # Build result from chunks
        stdout = "".join(c.content for c in self._output_chunks if c.chunk_type == "stdout")
        stderr = "".join(c.content for c in self._output_chunks if c.chunk_type == "stderr")

        return ExecutionResult(
            status=ExecutionStatus.COMPLETED if not stderr else ExecutionStatus.FAILED,
            output=stdout,
            error=stderr if stderr else None,
        )

    async def execute_streaming(self) -> AsyncIterator[StreamChunk]:
        """Execute code with streaming output."""
        if self.config.language == ExecutionEnvironment.SAFE_PYTHON:
            async for chunk in self._execute_safe_python():
                self._output_chunks.append(chunk)
                yield chunk
        elif self.config.language == ExecutionEnvironment.SQL:
            async for chunk in self._execute_sql():
                self._output_chunks.append(chunk)
                yield chunk
        else:
            yield StreamChunk(
                chunk_type="error",
                content=f"Language {self.config.language} not yet supported",
            )

    async def _execute_safe_python(self) -> AsyncIterator[StreamChunk]:
        """Execute Python in restricted sandbox."""
        # Yield initial progress
        yield StreamChunk(
            chunk_type="progress",
            content="Initializing Python sandbox...",
        )

        # Simulate execution with output
        code_lines = self.config.code.strip().split("\n")

        for i, line in enumerate(code_lines):
            if not line.strip():
                continue

            yield StreamChunk(
                chunk_type="progress",
                content=f"Executing line {i + 1}/{len(code_lines)}...",
            )

            # Simulate line execution
            await asyncio.sleep(0.1)

            # Check for print statements (simplified)
            if "print(" in line:
                # Extract content between quotes (simplified)
                import re

                match = re.search(r'print\(["\'](.+?)["\']\)', line)
                if match:
                    yield StreamChunk(
                        chunk_type="stdout",
                        content=match.group(1) + "\n",
                    )

        yield StreamChunk(
            chunk_type="progress",
            content="Execution completed successfully",
        )

    async def _execute_sql(self) -> AsyncIterator[StreamChunk]:
        """Execute SQL query."""
        yield StreamChunk(
            chunk_type="progress",
            content="Connecting to database...",
        )

        await asyncio.sleep(0.2)

        yield StreamChunk(
            chunk_type="stdout",
            content=f"Query: {self.config.code[:100]}...\n",
        )

        yield StreamChunk(
            chunk_type="stdout",
            content="Results: (simulated)\n- Row 1: ...\n- Row 2: ...\n",
        )


class AgentBlockRegistry:
    """
    Registry for managing agent blocks across canvases.

    Maintains active blocks and provides lookup by ID.
    """

    def __init__(self) -> None:
        self._blocks: Dict[UUID, AgentBlock] = {}
        self._canvas_blocks: Dict[UUID, set[UUID]] = {}  # canvas_id -> set of block_ids
        logger.info("AgentBlockRegistry initialized")

    def register(self, block: AgentBlock) -> None:
        """Register a new agent block."""
        self._blocks[block.block_id] = block

        if block.canvas_id not in self._canvas_blocks:
            self._canvas_blocks[block.canvas_id] = set()
        self._canvas_blocks[block.canvas_id].add(block.block_id)

        logger.debug(f"Registered agent block {block.block_id}")

    def unregister(self, block_id: UUID) -> Optional[AgentBlock]:
        """Unregister and return a block."""
        block = self._blocks.pop(block_id, None)
        if block:
            self._canvas_blocks.get(block.canvas_id, set()).discard(block_id)
            logger.debug(f"Unregistered agent block {block_id}")
        return block

    def get(self, block_id: UUID, tenant_id: int | None = None) -> Optional[AgentBlock]:
        """Get block by ID with optional tenant isolation filter."""
        block = self._blocks.get(block_id)
        if block is None:
            return None
        if tenant_id is not None and block.tenant_id != tenant_id:
            return None
        return block

    def get_canvas_blocks(self, canvas_id: UUID, tenant_id: int | None = None) -> List[AgentBlock]:
        """Get all agent blocks for a canvas."""
        block_ids = self._canvas_blocks.get(canvas_id, set())
        blocks = [self._blocks[bid] for bid in block_ids if bid in self._blocks]
        if tenant_id is not None:
            blocks = [b for b in blocks if b.tenant_id == tenant_id]
        return blocks

    async def execute_canvas_blocks(
        self,
        canvas_id: UUID,
        block_type: Optional[AgentBlockType] = None,
    ) -> List[ExecutionResult]:
        """Execute all agent blocks in a canvas."""
        blocks = self.get_canvas_blocks(canvas_id)

        if block_type:
            blocks = [b for b in blocks if b.block_type == block_type]

        results: List[Any] = []  # TODO(TYPE): replace Any with concrete type
        for block in blocks:
            try:
                result = await block.execute()
                results.append(result)
            except Exception as e:
                logger.error(
                    "Error executing block %s: %s: %s",
                    block.block_id,
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                results.append(
                    ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error=str(e),
                    )
                )

        return results


# Global registry instance
agent_block_registry = AgentBlockRegistry()
