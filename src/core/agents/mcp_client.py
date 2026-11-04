from __future__ import annotations

import json
import uuid
from typing import Any, Optional, Union, cast
from collections.abc import Mapping

from src.core.typing import SyncRedisClient
import redis as _redis_module
from opentelemetry import propagate

from src.config import config

# --- Constants ---
TASK_STREAM_NAME = "mcp_tasks"


# --- Custom Exceptions for better error handling ---
class MCPError(Exception):
    """Base exception for MCPClient errors."""


class MCPConnectionError(MCPError):
    """Raised when there is a problem connecting to Redis."""


class MCPTimeoutError(MCPError):
    """Raised when a task result does not arrive within the timeout period."""


class MCPTaskExecutionError(MCPError):
    """Raised when the remote worker reports an error during task execution."""


class MCPResultError(MCPError):
    """Raised when the result from the worker is malformed (e.g., invalid JSON)."""


class MCPClient:
    """
    Client SDK for Sub-Agents to interact with the asynchronous Tool Broker.
    """

    def __init__(self) -> None:
        """
        Initializes the MCPClient and establishes a connection to Redis.
        Raises:
            MCPConnectionError: If the connection to Redis fails.
        """
        self.redis_client: SyncRedisClient | None = None
        try:
            redis_url = config.get_redis_url()
            from src.core.typing import create_sync_redis_client

            client = create_sync_redis_client(redis_url, decode_responses=True)
            self.redis_client = client
            client.ping()
            print("MCPClient: Redis connection successful.")
        except (_redis_module.RedisError, ValueError) as e:
            self.redis_client = None  # Ensure client is None on failure
            raise MCPConnectionError(f"MCPClient: Error connecting to Redis: {e}") from e

    def execute_async(self, tool_name: str, payload: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Publishes a tool execution task to the Tool Broker asynchronously.

        Args:
            tool_name: The name of the tool to execute (e.g., 'serena__find_symbol').
            payload: The dictionary of parameters for the tool.

        Returns:
            The unique task_id for this execution request.

        Raises:
            MCPConnectionError: If the client is not connected to Redis or publishing fails.
        """
        if self.redis_client is None:
            raise MCPConnectionError("MCPClient is not connected to Redis. Cannot execute task.")

        task_id = str(uuid.uuid4())

        # --- OpenTelemetry Context Propagation ---
        trace_context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        propagate.inject(trace_context)

        # Serialize nested dicts to JSON strings for Redis stream compatibility
        task_data: dict[str, str] = {
            "task_id": task_id,
            "tool_name": tool_name,
            "payload": json.dumps(payload),
            "trace_context": json.dumps(trace_context),
        }

        try:
            # Publish the task to the Redis stream
            # Cast to Any to bypass invariant type parameters (FieldT/EncodableT)
            self.redis_client.xadd(TASK_STREAM_NAME, cast(Any, task_data))  # TODO(TYPE): replace Any with concrete type
            print(
                f"MCPClient: Task {task_id} for tool '{tool_name}' published to stream "
                f"'{TASK_STREAM_NAME}'."
            )
        except _redis_module.RedisError as e:
            # Catch potential errors during the xadd command (e.g., connection lost)
            raise MCPConnectionError(
                f"Failed to publish task {task_id} to Redis stream '{TASK_STREAM_NAME}': {e}"
            ) from e

        return task_id

    def get_result(self, task_id: str, timeout: int = 30) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Waits for and retrieves the result of a task execution.

        Args:
            task_id: The ID of the task to retrieve the result for.
            timeout: The maximum time to wait in seconds.

        Returns:
            A dictionary containing the successful task result.

        Raises:
            MCPConnectionError: If the client is not connected to Redis or the connection fails.
            MCPTimeoutError: If the result does not arrive within the timeout period.
            MCPResultError: If the received result is malformed (e.g., invalid JSON).
            MCPTaskExecutionError: If the worker reports that the task failed.
        """
        if self.redis_client is None:
            raise MCPConnectionError("MCPClient is not connected to Redis. Cannot get result.")

        result_key = f"mcp_results:{task_id}"
        print(f"MCPClient: Waiting for result of task {task_id} on key '{result_key}'...")

        try:
            # Use BLPOP to wait for the result. It returns a tuple (key, value).
            result: tuple[str, str] | None | Any = self.redis_client.blpop(  # TODO(TYPE): replace Any with concrete type
                [result_key], timeout=timeout
            )
        except _redis_module.RedisError as e:
            raise MCPConnectionError(
                f"Failed to retrieve result for task {task_id} from Redis: {e}"
            ) from e

        if result is None:
            raise MCPTimeoutError(
                f"Timed out after {timeout} seconds waiting for result for task {task_id}."
            )

        # result is a tuple: ('mcp_results:task_id', '{"status": ...}')
        _, result_json = cast(tuple[str, str], result)
        print(f"MCPClient: Result for task {task_id} received.")

        try:
            result_data: dict[str, Any] = json.loads(result_json)  # TODO(TYPE): replace Any with concrete type
        except json.JSONDecodeError as e:
            raise MCPResultError(f"Failed to decode result JSON for task {task_id}: {e}") from e

        # Check if the worker reported an error
        if result_data.get("status") == "error":
            error_message = result_data.get("error", "Unknown error from worker.")
            raise MCPTaskExecutionError(f"Task {task_id} failed on worker: {error_message}")

        return result_data


# Global client instance -- lazy initialization to avoid import-time side effects
mcp_client: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """Get or create the global MCPClient instance."""
    global mcp_client
    if mcp_client is None:
        mcp_client = MCPClient()
    return mcp_client
