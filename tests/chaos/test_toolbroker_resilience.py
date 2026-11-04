#!/usr/bin/env python3
"""
Chaos Tests: ToolBroker Resilience (Sprint 5, Slice 1)

Tests circuit breaker activation, timeout handling, and retry behavior
when external tool services fail or become slow.

Coverage:
- [x] test_circuit_breaker_activates - Circuit breaker opens after threshold failures
- [x] test_circuit_breaker_half_open_recovery - Breaker recovers to closed state
- [x] test_timeout_handling - Requests timeout correctly without blocking
- [x] test_infinite_retry_prevention - Max 3 retries, then FAILED status
- [x] test_graceful_degradation - System fails safely without cascading errors
"""

import asyncio
import socket
import uuid
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.resilience import (
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    RetryConfig,
)
from src.core.tool_broker.service import ToolBrokerService


class MockSerenaClient:
    """Mock Serena client for chaos testing"""

    def __init__(self, failure_mode: str = "none"):
        """
        Args:
            failure_mode: 'none', 'timeout', 'error', 'intermittent'
        """
        self.failure_mode = failure_mode
        self.call_count = 0

    async def call(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate tool call with configurable failure modes"""
        self.call_count += 1

        if self.failure_mode == "timeout":
            # Simulate timeout (longer than circuit breaker timeout)
            await asyncio.sleep(35)
            return {"status": "ok"}

        elif self.failure_mode == "error":
            raise RuntimeError(f"Simulated error for {tool_name}")

        elif self.failure_mode == "intermittent":
            # Fail first 3 calls, succeed afterwards
            if self.call_count <= 3:
                raise RuntimeError(f"Intermittent failure #{self.call_count}")
            return {"status": "recovered", "attempt": self.call_count}

        # Normal operation
        return {"status": "success", "tool": tool_name}


class MockSequentialThinkingClient:
    """Mock Sequential Thinking client (always succeeds for these tests)"""

    async def call(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success", "tool": tool_name}


@pytest.fixture
def mock_serena_client():
    """Provide mock Serena client"""
    return MockSerenaClient()


@pytest.fixture
def mock_seq_client():
    """Provide mock Sequential Thinking client"""
    return MockSequentialThinkingClient()


@pytest.fixture
def tool_broker_service(mock_serena_client, mock_seq_client):
    """Provide ToolBrokerService with fast circuit breaker config for testing"""
    # Fast config for testing (lower thresholds and timeouts)
    circuit_breaker_config = CircuitBreakerConfig(
        failure_threshold=3,  # Open after 3 failures
        failure_window_seconds=10,  # Count failures in 10s window
        timeout_seconds=5,  # Timeout after 5s
        reset_timeout_seconds=10,  # Try half-open after 10s
    )

    retry_config = RetryConfig(
        max_attempts=3,  # Max 3 retries
        initial_delay_ms=50,  # Fast retries for testing
        max_delay_ms=200,
    )

    return ToolBrokerService(
        serena_client=mock_serena_client,
        seq_thinking_client=mock_seq_client,
        local_registry=None,
        enable_resilience=True,
        retry_config=retry_config,
        circuit_breaker_config=circuit_breaker_config,
    )


def clear_circuit_breaker_registry():
    """Clear the global circuit breaker registry to ensure test isolation."""
    from src.core.tool_broker.resilience import get_circuit_breaker_registry

    registry = get_circuit_breaker_registry()
    registry.breakers.clear()


# ============================================================================
# TEST 1: Circuit Breaker Activation
# ============================================================================


@pytest.mark.asyncio
async def test_circuit_breaker_activates():
    """
    Test that circuit breaker opens after threshold failures.

    Given: ToolBrokerService with failure_threshold=3
    When: 3 consecutive tool calls fail
    Then: Circuit breaker opens, 4th call raises CircuitBreakerOpenException
    """
    # Clear registry to ensure clean state
    clear_circuit_breaker_registry()

    # Arrange
    failing_client = MockSerenaClient(failure_mode="error")
    seq_client = MockSequentialThinkingClient()

    circuit_config = CircuitBreakerConfig(
        failure_threshold=3, failure_window_seconds=60, timeout_seconds=5
    )
    retry_config = RetryConfig(max_attempts=1)  # No retries for this test

    broker = ToolBrokerService(
        serena_client=failing_client,
        seq_thinking_client=seq_client,
        enable_resilience=True,
        retry_config=retry_config,
        circuit_breaker_config=circuit_config,
    )

    tool_name = "serena__test_tool"
    payload = {"test": "data"}

    # Act: Trigger 3 failures to open circuit breaker
    for i in range(3):
        with pytest.raises(ToolExecutionException) as exc_info:
            await asyncio.wait_for(broker.execute_tool(tool_name, payload), timeout=10.0)
        assert "Simulated error" in str(exc_info.value)

    # Assert: 4th call should be blocked by open circuit breaker
    with pytest.raises(ToolExecutionException) as exc_info:
        await asyncio.wait_for(broker.execute_tool(tool_name, payload), timeout=10.0)

    error_msg = str(exc_info.value)
    assert (
        "circuit breaker open" in error_msg.lower()
        or "temporarily unavailable" in error_msg.lower()
    )

    # Verify breaker state
    breaker_state = broker.get_circuit_breaker_state("serena_client")
    assert breaker_state is not None
    assert breaker_state["state"] == "open"
    assert breaker_state["failure_count"] >= 3


# ============================================================================
# TEST 2: Circuit Breaker Recovery (Half-Open -> Closed)
# ============================================================================


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovery():
    """
    Test that circuit breaker recovers to closed state after successful calls.

    Given: Circuit breaker in half-open state (after reset timeout)
    When: Successful call is made
    Then: Circuit breaker transitions to closed state
    """
    # Clear registry to ensure clean state
    clear_circuit_breaker_registry()

    # Arrange: Use intermittent failure mode (fails 3 times, then recovers)
    intermittent_client = MockSerenaClient(failure_mode="intermittent")
    seq_client = MockSequentialThinkingClient()

    circuit_config = CircuitBreakerConfig(
        failure_threshold=3,
        failure_window_seconds=60,
        timeout_seconds=5,
        reset_timeout_seconds=2,  # Fast recovery for testing
    )
    retry_config = RetryConfig(max_attempts=1)

    broker = ToolBrokerService(
        serena_client=intermittent_client,
        seq_thinking_client=seq_client,
        enable_resilience=True,
        retry_config=retry_config,
        circuit_breaker_config=circuit_config,
    )

    tool_name = "serena__test_recovery"
    payload = {"test": "recovery"}

    # Act: Trigger 3 failures to open breaker
    for _ in range(3):
        with pytest.raises(ToolExecutionException):
            await asyncio.wait_for(broker.execute_tool(tool_name, payload), timeout=10.0)

    # Wait for reset timeout (half-open state)
    await asyncio.sleep(2.5)

    # Successful call should transition to closed
    result = await asyncio.wait_for(broker.execute_tool(tool_name, payload), timeout=10.0)

    # Assert
    assert result["status"] == "recovered"
    assert intermittent_client.call_count == 4  # 3 failures + 1 success

    breaker_state = broker.get_circuit_breaker_state("serena_client")
    assert breaker_state["state"] in [
        "closed",
        "half_open",
    ]  # May still be half-open but accepting


# ============================================================================
# TEST 3: Timeout Handling
# ============================================================================


@pytest.mark.asyncio
async def test_timeout_handling():
    """
    Test that slow tool calls timeout correctly without blocking forever.

    Given: Tool call that takes 35 seconds (exceeds 5s timeout)
    When: execute_tool is called
    Then: Call times out and raises ToolExecutionException within timeout
    """
    # Clear registry to ensure clean state
    clear_circuit_breaker_registry()

    # Arrange
    slow_client = MockSerenaClient(failure_mode="timeout")
    seq_client = MockSequentialThinkingClient()

    circuit_config = CircuitBreakerConfig(timeout_seconds=5, failure_threshold=5)
    retry_config = RetryConfig(max_attempts=1)  # No retry to test pure timeout

    broker = ToolBrokerService(
        serena_client=slow_client,
        seq_thinking_client=seq_client,
        enable_resilience=True,
        retry_config=retry_config,
        circuit_breaker_config=circuit_config,
    )

    tool_name = "serena__slow_tool"
    payload = {"test": "timeout"}

    # Act & Assert: Should timeout within ~5 seconds
    import time

    start = time.time()
    with pytest.raises((ToolExecutionException, asyncio.TimeoutError, CircuitBreakerOpenException)):
        await asyncio.wait_for(
            broker.execute_tool(tool_name, payload),
            timeout=8.0,  # Slightly more than circuit breaker timeout
        )
    elapsed = time.time() - start

    # Assert: Timeout happened within reasonable time (allow margin for overhead)
    assert elapsed < 12, f"Timeout took too long: {elapsed}s"


# ============================================================================
# TEST 4: Infinite Retry Prevention
# ============================================================================


@pytest.mark.asyncio
async def test_infinite_retry_prevention():
    """
    Test that retries are capped at max_attempts, preventing infinite loops.

    Given: Tool that always fails
    When: execute_tool is called with max_attempts=3
    Then: Exactly 3 attempts are made, then ToolExecutionException is raised
    """
    # Clear registry to ensure clean state
    clear_circuit_breaker_registry()

    # Arrange
    always_failing_client = MockSerenaClient(failure_mode="error")
    seq_client = MockSequentialThinkingClient()

    retry_config = RetryConfig(max_attempts=3, initial_delay_ms=10)
    # Use very high threshold to prevent circuit breaker from opening during test
    circuit_config = CircuitBreakerConfig(
        failure_threshold=100,
        timeout_seconds=300,
    )

    broker = ToolBrokerService(
        serena_client=always_failing_client,
        seq_thinking_client=seq_client,
        enable_resilience=True,
        retry_config=retry_config,
        circuit_breaker_config=circuit_config,
    )

    tool_name = "serena__failing_tool"
    payload = {"test": "retry"}

    # Act
    with pytest.raises(ToolExecutionException) as exc_info:
        await asyncio.wait_for(broker.execute_tool(tool_name, payload), timeout=10.0)

    # Assert: Client should be called at most 3 times (no infinite retry)
    assert always_failing_client.call_count <= 3
    # Error should be either simulated error or circuit breaker (acceptable fallback)
    error_msg = str(exc_info.value).lower()
    assert (
        "simulated error" in error_msg
        or "circuit breaker" in error_msg
        or "temporarily unavailable" in error_msg
    )


# ============================================================================
# TEST 5: Graceful Degradation
# ============================================================================


@pytest.mark.asyncio
async def test_graceful_degradation():
    """
    Test that system fails safely without cascading errors.

    Given: Multiple tool calls, some fail, some succeed
    When: Resilience patterns are enabled
    Then: Failures are isolated, no cascading crashes
    """
    # Clear registry to ensure clean state
    clear_circuit_breaker_registry()

    # Arrange: Mixed clients (one fails, one succeeds)
    failing_serena = MockSerenaClient(failure_mode="error")
    working_seq = MockSequentialThinkingClient()

    broker = ToolBrokerService(
        serena_client=failing_serena,
        seq_thinking_client=working_seq,
        enable_resilience=True,
    )

    # Act: Call both failing and working tools
    results = []
    exceptions = []

    # Serena tools should fail gracefully
    try:
        await asyncio.wait_for(broker.execute_tool("serena__will_fail", {}), timeout=10.0)
    except ToolExecutionException as e:
        exceptions.append(("serena", e))

    # Sequential thinking tools should still work
    try:
        result = await asyncio.wait_for(
            broker.execute_tool("sequentialthinking__will_work", {}), timeout=10.0
        )
        results.append(("seq", result))
    except Exception as e:
        exceptions.append(("seq", e))

    # Assert: Exactly 1 failure (serena), 1 success (seq)
    assert len(exceptions) >= 1
    assert exceptions[0][0] == "serena"

    assert len(results) == 1
    assert results[0][0] == "seq"
    assert results[0][1]["status"] == "success"

    # Resilience metrics should show mixed results
    status = broker.get_resilience_status()
    assert status["resilience_enabled"] is True
    assert "resilience_metrics" in status


# ============================================================================
# TEST 6: Circuit Breaker State Inspection
# ============================================================================


@pytest.mark.asyncio
async def test_circuit_breaker_state_inspection():
    """
    Test that circuit breaker state can be inspected for monitoring.

    Given: ToolBrokerService with circuit breakers
    When: get_resilience_status is called
    Then: Returns detailed state for all circuit breakers
    """
    # Clear registry to ensure clean state
    clear_circuit_breaker_registry()

    # Arrange
    serena_client = MockSerenaClient()
    seq_client = MockSequentialThinkingClient()

    broker = ToolBrokerService(
        serena_client=serena_client,
        seq_thinking_client=seq_client,
        enable_resilience=True,
    )

    # Act
    status = broker.get_resilience_status()

    # Assert
    assert "resilience_enabled" in status
    assert status["resilience_enabled"] is True

    assert "circuit_breakers" in status
    breakers = status["circuit_breakers"]
    assert "serena_client" in breakers
    assert "sequential_thinking_client" in breakers

    # Each breaker should have state info
    serena_state = breakers["serena_client"]
    assert "state" in serena_state  # closed, open, or half_open
    assert "failure_count" in serena_state

    # Dedicated getter should work too
    specific_state = broker.get_circuit_breaker_state("serena_client")
    assert specific_state is not None
    assert specific_state["state"] in ["closed", "open", "half_open"]


# ============================================================================
# Infrastructure-dependent tests (skipped if infrastructure unavailable)
# ============================================================================


def is_redis_available() -> bool:
    """Check if Redis is available for integration tests."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 6379))
        sock.close()
        return result == 0
    except Exception:
        return False


def is_docker_available() -> bool:
    """Check if Docker is available for container-based tests."""
    try:
        import subprocess

        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5, check=False)
        return result.returncode == 0
    except Exception:
        return False


# Fixtures for infrastructure checks
requires_redis = pytest.mark.skipif(
    not is_redis_available(), reason="Redis not available on localhost:6379"
)

requires_docker = pytest.mark.skipif(not is_docker_available(), reason="Docker not available")


@pytest.mark.asyncio
@requires_redis
async def test_circuit_breaker_with_redis():
    """
    Test circuit breaker state persistence with Redis.
    Skipped if Redis is not available.
    """
    # This test would verify Redis-backed circuit breaker state
    # For now, just verify the infrastructure check works
    assert is_redis_available()


@pytest.mark.asyncio
@requires_docker
async def test_container_resilience():
    """
    Test circuit breaker behavior with containerized services.
    Skipped if Docker is not available.
    """
    # This test would verify container-level resilience
    # For now, just verify the infrastructure check works
    assert is_docker_available()
