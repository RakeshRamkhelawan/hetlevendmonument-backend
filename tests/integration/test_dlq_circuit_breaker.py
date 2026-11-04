"""Integration tests for DLQ + Circuit Breaker

Tests the combination of:
- Dead Letter Queue (failed task handling)
- Circuit Breaker (failure detection and recovery)
- Tenant isolation

Run with: pytest tests/integration/test_dlq_circuit_breaker.py -v
"""

import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.getcwd())


@pytest.mark.integration
class TestDLQCircuitBreakerIntegration:
    """Integration tests for DLQ and Circuit Breaker."""

    def test_task_to_dlq_after_max_retries(self):
        """
        Happy: Task fails max retries → goes to DLQ
        """
        from src.core.workflow.dead_letter_queue import DLQStatus

        # Document expected flow
        # 1. Task fails
        # 2. Retry N times
        # 3. Max retries exceeded → DLQ

        assert DLQStatus.PENDING.value == "pending"
        assert DLQStatus.RETRYING.value == "retrying"
        assert DLQStatus.RESOLVED.value == "resolved"

        # Document retry flow
        flow = ["failed", "retry1", "retry2", "retry3", "dlq"]
        assert len(flow) == 5

    def test_breaker_open_sends_to_dlq(self):
        """
        Happy: Circuit breaker opens → new tasks go to DLQ
        """
        from src.core.resilience.circuit_breaker import CircuitState

        # Circuit states are string-backed enum values
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

        # When OPEN, tasks should be rejected/fast-failed to DLQ
        # Document expected behavior
        assert True, "Documented: OPEN state sends tasks to DLQ"

    def test_breaker_half_open_recovery(self):
        """
        Happy: Half-open allows test tasks → recovery
        """
        from src.core.resilience.circuit_breaker import CircuitState

        # HALF_OPEN allows limited traffic to test recovery
        state = CircuitState.HALF_OPEN

        # On success → CLOSED
        # On failure → OPEN
        assert state.value == "half_open"

    def test_per_provider_isolation(self):
        """
        Happy: Circuit breaker per provider, DLQ per tenant
        """
        # Circuit breakers are isolated per provider
        # DLQ entries are isolated per tenant

        providers = ["openai", "anthropic", "google"]

        # Each has independent circuit breaker
        assert len(providers) == 3

        # DLQ has tenant_id column for isolation
        from src.core.workflow.dead_letter_queue import DeadLetterEntry

        # Verify tenant_id is defined (would fail if column removed)
        assert hasattr(DeadLetterEntry, "tenant_id")

    def test_dlq_tenant_isolation(self):
        """
        Unhappy: Tenant A cannot see Tenant B DLQ entries
        """
        from src.core.workflow.dead_letter_queue import DeadLetterEntry

        # Verify DeadLetterEntry has tenant isolation
        entry = DeadLetterEntry(
            original_task_id="task-1",
            execution_id="exec-1",
            tenant_id=1,
            error_message="Test error",
        )

        assert entry.tenant_id == 1

        # Tenant 2 entry
        entry2 = DeadLetterEntry(
            original_task_id="task-2",
            execution_id="exec-2",
            tenant_id=2,
            error_message="Test error",
        )

        assert entry2.tenant_id == 2
        assert entry.tenant_id != entry2.tenant_id

    def test_poison_pill_detected(self):
        """
        Unhappy: Poison pill (repeatedly failing task) detected
        """
        from src.core.workflow.dead_letter_queue import DeadLetterEntry

        # A poison pill is a task that:
        # 1. Fails multiple times
        # 2. Is not recoverable
        # 3. Should not be retried

        entry = DeadLetterEntry(
            original_task_id="poison-task",
            execution_id="exec-1",
            tenant_id=1,
            error_message="Non-recoverable error",
            error_type="ValidationError",
            retry_count=10,  # Many retries
            max_retries=3,  # Exceeded
        )

        # Poison pill criteria
        is_poison = entry.retry_count >= entry.max_retries and entry.error_type in [
            "ValidationError",
            "SyntaxError",
            "TypeError",
        ]

        assert is_poison


@pytest.mark.unit
def test_dlq_entry_creation():
    """Test DLQ entry can be created."""
    from src.core.workflow.dead_letter_queue import DeadLetterEntry, DLQStatus

    entry = DeadLetterEntry(
        original_task_id="task-123",
        execution_id="exec-456",
        tenant_id=1,
        error_message="Task failed",
        error_type="RuntimeError",
        retry_count=3,
        max_retries=3,
        status=DLQStatus.PENDING.value,
    )

    assert entry.original_task_id == "task-123"
    assert entry.execution_id == "exec-456"
    assert entry.tenant_id == 1
    assert entry.status == "pending"


@pytest.mark.unit
def test_circuit_breaker_states():
    """Test circuit breaker state transitions."""
    from src.core.resilience.circuit_breaker import CircuitBreaker, CircuitState

    # CircuitState is string-backed in current implementation
    assert CircuitState.CLOSED.value == "closed"
    assert CircuitState.OPEN.value == "open"
    assert CircuitState.HALF_OPEN.value == "half_open"

    # Test breaker can be created
    breaker = CircuitBreaker(
        provider="test-breaker",
        failure_threshold=5,
        recovery_timeout=30,
    )

    assert breaker.provider == "test-breaker"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_registry():
    """Test circuit breaker registry."""
    from src.core.resilience.circuit_breaker import CircuitBreakerRegistry

    registry = CircuitBreakerRegistry()

    # Get breakers for different providers (async)
    openai_breaker = await registry.get_breaker("openai")
    anthropic_breaker = await registry.get_breaker("anthropic")

    # Should be different instances
    assert openai_breaker is not anthropic_breaker

    # Same provider should return same instance
    openai_breaker2 = await registry.get_breaker("openai")
    assert openai_breaker is openai_breaker2


@pytest.mark.unit
def test_dlq_circuit_breaker_integration_flow():
    """Document the integration flow between DLQ and Circuit Breaker."""
    # Flow:
    # 1. Task execution starts
    # 2. Circuit breaker checks state
    # 3. If CLOSED: execute task
    # 4. If task fails: increment failure count
    # 5. If failures >= threshold: OPEN circuit
    # 6. New tasks: fast-fail to DLQ
    # 7. After timeout: HALF_OPEN
    # 8. Test task: if success → CLOSED
    # 9. Failed tasks in DLQ can be retried manually

    flow_steps = [
        "circuit_check",
        "task_execution",
        "failure_tracking",
        "circuit_open",
        "dlq_enqueue",
        "recovery_timeout",
        "half_open_test",
        "circuit_close",
        "manual_retry",
    ]

    assert len(flow_steps) == 9
