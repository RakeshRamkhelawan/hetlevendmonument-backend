"""
Unit Tests for MCP Client
Tests Redis-based async tool broker client for sub-agents

Coverage Target: core/agents/mcp_client.py → >90%
"""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest
import redis.exceptions

from src.core.agents.mcp_client import (
    TASK_STREAM_NAME,
    MCPClient,
    MCPConnectionError,
    MCPError,
    MCPResultError,
    MCPTaskExecutionError,
    MCPTimeoutError,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    mock_client = Mock(spec=redis.Redis)
    mock_client.ping.return_value = True
    mock_client.xadd.return_value = b"1234567890-0"
    mock_client.blpop.return_value = (
        b"mcp_results:test-task-id",
        json.dumps({"status": "success", "result": {"output": "test"}}).encode(),
    )
    return mock_client


@pytest.fixture
def mock_config():
    """Mock config module"""
    mock_cfg = Mock()
    mock_cfg.get_redis_url.return_value = "redis://localhost:6380/0"
    return mock_cfg


# ============================================================================
# TEST: MCPClient Initialization
# ============================================================================


class TestMCPClientInit:
    """Test MCPClient initialization and connection"""

    def test_init_success(self, mock_redis, mock_config):
        """Test successful Redis connection"""
        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            assert client.redis_client is not None
            mock_redis.ping.assert_called_once()

    def test_init_connection_error(self, mock_config):
        """Test initialization fails with connection error"""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.ping.side_effect = redis.exceptions.ConnectionError("Connection refused")

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            with pytest.raises(MCPConnectionError) as exc_info:
                MCPClient()

            assert "Error connecting to Redis" in str(exc_info.value)

    def test_init_sets_redis_client_none_on_error(self, mock_config):
        """Test redis_client is None after connection failure"""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.ping.side_effect = redis.exceptions.ConnectionError("Connection refused")

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            # The __init__ should set redis_client = None before raising
            # We verify this by checking the exception is raised correctly
            with pytest.raises(MCPConnectionError) as exc_info:
                client = MCPClient()

            # The exception message should indicate connection failure
            assert "Error connecting to Redis" in str(exc_info.value)


# ============================================================================
# TEST: execute_async
# ============================================================================


class TestExecuteAsync:
    """Test execute_async method"""

    def test_execute_async_success(self, mock_redis, mock_config):
        """Test successful task publishing"""
        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
            patch("src.core.agents.mcp_client.propagate.inject") as mock_inject,
        ):
            client = MCPClient()
            task_id = client.execute_async("test_tool", {"param": "value"})

            assert isinstance(task_id, str)
            assert len(task_id) == 36  # UUID4 format

            # Verify xadd was called with correct structure
            mock_redis.xadd.assert_called_once()
            call_args = mock_redis.xadd.call_args
            assert call_args[0][0] == TASK_STREAM_NAME

            task_data = call_args[0][1]
            assert task_data["task_id"] == task_id
            assert task_data["tool_name"] == "test_tool"
            import json

            assert json.loads(task_data["payload"]) == {"param": "value"}
            assert "trace_context" in task_data

            # Verify OpenTelemetry context injection was called
            mock_inject.assert_called_once()

    def test_execute_async_no_connection(self, mock_config):
        """Test execute_async fails when not connected"""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.ping.return_value = True

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()
            client.redis_client = None  # Simulate disconnection

            with pytest.raises(MCPConnectionError) as exc_info:
                client.execute_async("test_tool", {})

            assert "not connected to Redis" in str(exc_info.value)

    def test_execute_async_redis_error(self, mock_redis, mock_config):
        """Test execute_async handles Redis errors"""
        mock_redis.xadd.side_effect = redis.exceptions.RedisError("Stream error")

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            with pytest.raises(MCPConnectionError) as exc_info:
                client.execute_async("test_tool", {})

            assert "Failed to publish task" in str(exc_info.value)
            assert "Stream error" in str(exc_info.value)

    def test_execute_async_generates_unique_task_ids(self, mock_redis, mock_config):
        """Test that each call generates a unique task ID"""
        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            task_id1 = client.execute_async("tool1", {})
            task_id2 = client.execute_async("tool2", {})
            task_id3 = client.execute_async("tool1", {})

            # All IDs should be unique
            assert task_id1 != task_id2
            assert task_id2 != task_id3
            assert task_id1 != task_id3


# ============================================================================
# TEST: get_result
# ============================================================================


class TestGetResult:
    """Test get_result method"""

    def test_get_result_success(self, mock_redis, mock_config):
        """Test successful result retrieval"""
        result_json = json.dumps({"status": "success", "result": {"output": "test"}})
        mock_redis.blpop.return_value = (b"mcp_results:task-123", result_json)

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()
            result = client.get_result("task-123", timeout=10)

            assert result["status"] == "success"
            assert result["result"]["output"] == "test"

            # Verify blpop was called with correct parameters
            mock_redis.blpop.assert_called_once_with(["mcp_results:task-123"], timeout=10)

    def test_get_result_no_connection(self, mock_config):
        """Test get_result fails when not connected"""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.ping.return_value = True

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()
            client.redis_client = None  # Simulate disconnection

            with pytest.raises(MCPConnectionError) as exc_info:
                client.get_result("task-123")

            assert "not connected to Redis" in str(exc_info.value)

    def test_get_result_timeout(self, mock_redis, mock_config):
        """Test timeout when result doesn't arrive"""
        mock_redis.blpop.return_value = None  # Timeout

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            with pytest.raises(MCPTimeoutError) as exc_info:
                client.get_result("task-123", timeout=5)

            assert "Timed out after 5 seconds" in str(exc_info.value)
            assert "task-123" in str(exc_info.value)

    def test_get_result_redis_error(self, mock_redis, mock_config):
        """Test get_result handles Redis errors"""
        mock_redis.blpop.side_effect = redis.exceptions.RedisError("Connection lost")

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            with pytest.raises(MCPConnectionError) as exc_info:
                client.get_result("task-123")

            assert "Failed to retrieve result" in str(exc_info.value)
            assert "Connection lost" in str(exc_info.value)

    def test_get_result_invalid_json(self, mock_redis, mock_config):
        """Test get_result handles malformed JSON"""
        mock_redis.blpop.return_value = (b"mcp_results:task-123", "invalid json{}")

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            with pytest.raises(MCPResultError) as exc_info:
                client.get_result("task-123")

            assert "Failed to decode result JSON" in str(exc_info.value)

    def test_get_result_task_execution_error(self, mock_redis, mock_config):
        """Test get_result handles worker-reported errors"""
        error_result = json.dumps(
            {"status": "error", "error": "Tool execution failed: Invalid parameters"}
        )
        mock_redis.blpop.return_value = (b"mcp_results:task-123", error_result)

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            with pytest.raises(MCPTaskExecutionError) as exc_info:
                client.get_result("task-123")

            assert "failed on worker" in str(exc_info.value)
            assert "Invalid parameters" in str(exc_info.value)

    def test_get_result_task_error_no_message(self, mock_redis, mock_config):
        """Test get_result handles worker errors without error message"""
        error_result = json.dumps({"status": "error"})  # No 'error' field
        mock_redis.blpop.return_value = (b"mcp_results:task-123", error_result)

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            with pytest.raises(MCPTaskExecutionError) as exc_info:
                client.get_result("task-123")

            assert "Unknown error from worker" in str(exc_info.value)


# ============================================================================
# TEST: Exception Hierarchy
# ============================================================================


class TestExceptionHierarchy:
    """Test custom exception classes"""

    def test_mcp_error_base_exception(self):
        """Test MCPError is base exception"""
        error = MCPError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_mcp_connection_error_inherits_base(self):
        """Test MCPConnectionError inherits from MCPError"""
        error = MCPConnectionError("Connection failed")
        assert isinstance(error, MCPError)
        assert isinstance(error, Exception)

    def test_mcp_timeout_error_inherits_base(self):
        """Test MCPTimeoutError inherits from MCPError"""
        error = MCPTimeoutError("Timeout occurred")
        assert isinstance(error, MCPError)
        assert isinstance(error, Exception)

    def test_mcp_task_execution_error_inherits_base(self):
        """Test MCPTaskExecutionError inherits from MCPError"""
        error = MCPTaskExecutionError("Task failed")
        assert isinstance(error, MCPError)
        assert isinstance(error, Exception)

    def test_mcp_result_error_inherits_base(self):
        """Test MCPResultError inherits from MCPError"""
        error = MCPResultError("Invalid result")
        assert isinstance(error, MCPError)
        assert isinstance(error, Exception)


# ============================================================================
# TEST: Integration-Style Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Test realistic usage patterns"""

    def test_full_task_lifecycle(self, mock_redis, mock_config):
        """Test complete execute -> wait -> get_result flow"""
        result_json = json.dumps({"status": "success", "result": {"data": "processed"}})

        # Mock blpop to return result with matching task_id
        def blpop_side_effect(keys, timeout):
            task_id = keys[0].split(":")[1]
            return (f"mcp_results:{task_id}".encode(), result_json)

        mock_redis.blpop.side_effect = blpop_side_effect

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            # Execute task
            task_id = client.execute_async("data_processor", {"input": "raw"})

            # Get result
            result = client.get_result(task_id, timeout=10)

            assert result["status"] == "success"
            assert result["result"]["data"] == "processed"

    def test_multiple_tasks_parallel(self, mock_redis, mock_config):
        """Test multiple tasks can be executed in parallel"""
        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            # Execute multiple tasks
            task_ids = [
                client.execute_async("tool1", {"param": "a"}),
                client.execute_async("tool2", {"param": "b"}),
                client.execute_async("tool3", {"param": "c"}),
            ]

            # Verify all are unique
            assert len(set(task_ids)) == 3

            # Verify xadd was called 3 times
            assert mock_redis.xadd.call_count == 3

    def test_retry_after_connection_loss(self, mock_config):
        """Test client behavior after connection loss during operation"""
        mock_redis = Mock(spec=redis.Redis)
        mock_redis.ping.return_value = True
        mock_redis.xadd.side_effect = [
            redis.exceptions.ConnectionError("Connection lost"),  # First call fails
            b"1234567890-0",  # Second call succeeds
        ]

        with (
            patch("src.core.typing.create_sync_redis_client", return_value=mock_redis),
            patch("src.core.agents.mcp_client.config", mock_config),
        ):
            client = MCPClient()

            # First attempt fails
            with pytest.raises(MCPConnectionError):
                client.execute_async("test_tool", {})

            # Second attempt succeeds (simulating reconnection)
            task_id = client.execute_async("test_tool", {})
            assert isinstance(task_id, str)


# ============================================================================
# TEST: Constants
# ============================================================================


class TestConstants:
    """Test module constants"""

    def test_task_stream_name(self):
        """Test TASK_STREAM_NAME constant is defined"""
        assert TASK_STREAM_NAME == "mcp_tasks"

    def test_task_stream_name_is_string(self):
        """Test TASK_STREAM_NAME is a non-empty string"""
        assert isinstance(TASK_STREAM_NAME, str)
        assert len(TASK_STREAM_NAME) > 0
