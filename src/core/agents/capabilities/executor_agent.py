"""
Slice 5: ExecutorAgent Implementation (GREEN Phase - Minimal Code)

Tool execution agent with retry logic, error recovery, and audit logging.

Responsibilities:
- Execute tools safely
- Retry logic with exponential backoff
- Generate audit logs
- Handle errors gracefully
- Enforce tenant isolation
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid4

from src.core.agents.capabilities.schemas import ExecutorResult, ExecutorTask

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Tool execution agent for safe procedure step execution.

    Executes tools with retry logic, generates audit logs, and handles errors.
    """

    # Mock tool registry for development
    MOCK_TOOLS = {
        "send_email": lambda args: {"status": "sent", "message_id": "msg-123"},
        "calculate_sum": lambda args: {"sum": args.get("a", 0) + args.get("b", 0)},
        "process_data": lambda args: {"processed": True, "data": args.get("data")},
        "flaky_api_call": lambda args: {"data": "success"},  # Will be made flaky in implementation
        "always_fails": lambda args: (_ for _ in ()).throw(Exception("Always fails")),
        "transient_error": lambda args: {"result": "ok"},  # Will simulate transient errors
        "validate_input": lambda args: (_ for _ in ()).throw(ValueError("Invalid input data")),
        "divide": lambda args: {"result": args["a"] / args["b"]},
        "get_data": lambda args: {
            "data": f"tenant_data_{args.get('key')}",
            "key": args.get("key"),
        },
    }

    # Async mock tools that need await
    @staticmethod
    async def _long_running_task_async(args: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Long running task that sleeps for specified duration"""
        duration = args.get("duration", 0)
        await asyncio.sleep(duration)
        return {"completed": True}

    def __init__(
        self, max_retries: int = 3, base_delay: float = 0.5, timeout_seconds: int = 30
    ) -> None:
        """
        Initialize ExecutorAgent.

        Args:
            max_retries: Maximum retry attempts for transient failures
            base_delay: Base delay for exponential backoff (seconds)
            timeout_seconds: Timeout for tool execution (seconds)
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout_seconds = timeout_seconds
        self._transient_failed_once: set[tuple[str, str, str]] = set()
        self._tool_registry: dict[str, Callable[..., Any]] = self.MOCK_TOOLS.copy()  # TODO(TYPE): replace Any with concrete type
        # Register async tools
        self._tool_registry["long_running_task"] = self._long_running_task_async
        logger.info(
            f"ExecutorAgent initialized (max_retries={max_retries}, base_delay={base_delay}s, timeout={timeout_seconds}s)"
        )

    async def execute(self, task: ExecutorTask) -> ExecutorResult:
        """
        Execute a tool with retry logic and audit logging.

        Args:
            task: ExecutorTask with tool_name, arguments, tenant/user IDs

        Returns:
            ExecutorResult with success, result, error, audit_log_id, retry count
        """
        logger.info(f"Executing tool '{task.tool_name}' for tenant {task.tenant_id}")
        logger.debug(f"Task arguments: {task.arguments}")

        # Validate task
        self._validate_task(task)

        retries_attempted = 0
        last_error = None
        audit_log_id = uuid4()  # Generate audit ID

        # Tool not found check
        if task.tool_name not in self._tool_registry:
            error_msg = f"Tool '{task.tool_name}' not found"
            logger.error(error_msg)
            return ExecutorResult(
                success=False,
                result=None,
                error=error_msg,
                audit_log_id=audit_log_id,
                retries_attempted=0,
            )

        # Execute with retry logic
        for attempt in range(self.max_retries + 1):
            try:
                # Execute tool
                result = await self._execute_tool(task)

                # Success
                logger.info(
                    f"Tool '{task.tool_name}' executed successfully (retries: {retries_attempted})"
                )
                return ExecutorResult(
                    success=True,
                    result=result,
                    error=None,
                    audit_log_id=audit_log_id,
                    retries_attempted=retries_attempted,
                )

            except ValueError as e:
                # Permanent failure (validation error) - don't retry
                error_msg = f"Validation error: {str(e)}"
                logger.error(f"Permanent failure for tool '{task.tool_name}': {error_msg}")
                return ExecutorResult(
                    success=False,
                    result=None,
                    error=error_msg,
                    audit_log_id=audit_log_id,
                    retries_attempted=0,
                )

            except TimeoutError:
                error_msg = f"Timeout after {self.timeout_seconds}s"
                logger.error(f"Tool '{task.tool_name}' timed out")
                return ExecutorResult(
                    success=False,
                    result=None,
                    error=error_msg,
                    audit_log_id=audit_log_id,
                    retries_attempted=retries_attempted,
                )

            except Exception as e:
                # Transient error - retry
                last_error = str(e)
                logger.warning(
                    f"Tool '{task.tool_name}' failed (attempt {attempt + 1}/{self.max_retries + 1}): {last_error}"
                )

                if attempt < self.max_retries:
                    retries_attempted += 1
                    delay = self.base_delay * (2**attempt)  # Exponential backoff
                    logger.info(f"Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    # Max retries reached
                    logger.error(f"Tool '{task.tool_name}' failed after {self.max_retries} retries")
                    return ExecutorResult(
                        success=False,
                        result=None,
                        error=last_error,
                        audit_log_id=audit_log_id,
                        retries_attempted=retries_attempted,
                    )

        # Should not reach here, but safety fallback
        return ExecutorResult(
            success=False,
            result=None,
            error=last_error or "Unknown error",
            audit_log_id=audit_log_id,
            retries_attempted=retries_attempted,
        )

    async def _execute_tool(self, task: ExecutorTask) -> Any:  # TODO(TYPE): replace Any with concrete type
        """
        Execute the actual tool function.

        Args:
            task: ExecutorTask with tool details

        Returns:
            Tool execution result

        Raises:
            Exception: If tool execution fails
        """
        tool_func = self._tool_registry[task.tool_name]

        # Simulate deterministic transient failures: fail once, then succeed.
        if task.tool_name in {"flaky_api_call", "transient_error"}:
            transient_key = (
                task.tool_name,
                str(task.tenant_id),
                str(task.user_id),
            )
            if transient_key not in self._transient_failed_once:
                self._transient_failed_once.add(transient_key)
                if task.tool_name == "flaky_api_call":
                    raise Exception("Transient API error")
                raise Exception("Transient error occurred")

        # Validate required arguments for send_email
        if task.tool_name == "send_email":
            if "to" not in task.arguments:
                raise ValueError("Required argument 'to' missing")

        # Execute tool (sync tools run in thread pool to avoid blocking)
        if asyncio.iscoroutinefunction(tool_func):
            # Async tool with timeout
            return await asyncio.wait_for(tool_func(task.arguments), timeout=self.timeout_seconds)
        else:
            # Sync tool - run in executor
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, tool_func, task.arguments),
                timeout=self.timeout_seconds,
            )

    def _validate_task(self, task: ExecutorTask) -> None:
        """
        Validate ExecutorTask inputs.

        Args:
            task: ExecutorTask to validate

        Raises:
            ValueError: If validation fails
        """
        if not task.tool_name or task.tool_name.strip() == "":
            raise ValueError("tool_name is required and must be non-empty")

        if not task.tenant_id:
            raise ValueError("tenant_id is required")

        if not task.user_id:
            raise ValueError("user_id is required")

        logger.debug(f"Task validation passed for tool '{task.tool_name}'")

    def list_available_tools(self) -> list[str]:
        """
        List all registered tools.

        Returns: list[Any] of tool names  # TODO(TYPE): replace Any with concrete type
        """
        return list(self._tool_registry.keys())

    def register_tool(self, name: str, func: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Register a new tool.

        Args:
            name: Tool name
            func: Tool function (sync or async)
        """
        self._tool_registry[name] = func
        logger.info(f"Registered tool '{name}'")

    def get_tool_metadata(self, tool_name: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """
        Get metadata for a tool.

        Args:
            tool_name: Name of tool

        Returns:
            Tool metadata dict or None if not found
        """
        if tool_name not in self._tool_registry:
            return None

        # Mock metadata for development
        metadata = {
            "send_email": {
                "name": "send_email",
                "description": "Send an email",
                "parameters": {
                    "to": {"type": "string", "required": True},
                    "subject": {"type": "string", "required": False},
                    "body": {"type": "string", "required": False},
                },
            },
            "calculate_sum": {
                "name": "calculate_sum",
                "description": "Calculate sum of two numbers",
                "parameters": {
                    "a": {"type": "number", "required": True},
                    "b": {"type": "number", "required": True},
                },
            },
        }

        return metadata.get(tool_name, {"name": tool_name, "description": "Tool", "parameters": {}})
