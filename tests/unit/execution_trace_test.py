"""
TDD Tests for TKT-F0-03: Execution Trace Contract
Phase 0 - Contract Foundation

Tests: Happy + 2 Unhappy paths
"""

import time
from datetime import datetime
from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from src.core.contracts.trace import ExecutionTrace, TraceEvent, TraceOutcome, TraceStore
from src.core.contracts.trace_collector import TraceCollector


class TestExecutionTrace:
    """Happy and unhappy tests for execution trace"""

    def test_happy_successful_step_writes_complete_trace(self):
        """Happy: successful step writes complete trace"""
        # Arrange
        trace = ExecutionTrace(
            trace_id="trace-001",
            tenant_id="tenant-123",
            workflow_id="workflow-456",
            capability_key="email.send",
            decision_reason="Policy allowed execution",
            approval_state="not_required",
            fallback_used=False,
            outcome=TraceOutcome.SUCCESS,
            latency_ms=150,
            metadata={"recipient": "test@example.com"},
        )

        # Assert
        assert trace.trace_id == "trace-001"
        assert trace.tenant_id == "tenant-123"
        assert trace.workflow_id == "workflow-456"
        assert trace.capability_key == "email.send"
        assert trace.decision_reason == "Policy allowed execution"
        assert trace.approval_state == "not_required"
        assert trace.fallback_used is False
        assert trace.outcome == TraceOutcome.SUCCESS
        assert trace.latency_ms == 150
        assert trace.timestamp is not None

    def test_unhappy_fallback_activated_trace_shows_fallback(self):
        """Unhappy 1: fallback activated -> fallback_used=true + provider switch visible"""
        # Arrange
        trace = ExecutionTrace(
            trace_id="trace-002",
            tenant_id="tenant-123",
            workflow_id="workflow-456",
            capability_key="email.send_backup",  # Fallback capability
            decision_reason="Primary provider failed, fallback activated",
            approval_state="not_required",
            fallback_used=True,
            primary_provider="sendgrid",
            fallback_provider="aws_ses",
            outcome=TraceOutcome.SUCCESS,
            latency_ms=320,
            metadata={"fallback_reason": "Primary timeout"},
        )

        # Assert
        assert trace.fallback_used is True
        assert trace.primary_provider == "sendgrid"
        assert trace.fallback_provider == "aws_ses"
        assert trace.decision_reason == "Primary provider failed, fallback activated"
        assert "fallback_reason" in trace.metadata

    def test_unhappy_hard_failure_trace_shows_failure_context(self):
        """Unhappy 2: hard failure -> outcome=failed with error context"""
        # Arrange
        trace = ExecutionTrace(
            trace_id="trace-003",
            tenant_id="tenant-123",
            workflow_id="workflow-456",
            capability_key="payment.charge",
            decision_reason="Execution failed after max retries",
            approval_state="not_required",
            fallback_used=False,
            outcome=TraceOutcome.FAILED,
            latency_ms=5000,
            error_code="PROVIDER_ERROR",
            error_message="Payment gateway returned 500",
            error_context={"provider": "stripe", "status_code": 500, "retry_count": 3},
        )

        # Assert
        assert trace.outcome == TraceOutcome.FAILED
        assert trace.error_code == "PROVIDER_ERROR"
        assert trace.error_message == "Payment gateway returned 500"
        assert trace.error_context["provider"] == "stripe"
        assert trace.error_context["retry_count"] == 3


class TestTraceCollector:
    """Tests for trace collection during workflow execution"""

    @pytest.fixture
    def collector(self):
        """Create trace collector with mock store"""
        mock_store = Mock(spec=TraceStore)
        return TraceCollector(store=mock_store)

    def test_happy_collector_creates_trace_for_success(self, collector):
        """Happy: collector creates complete trace for successful execution"""
        # Arrange
        context = {
            "trace_id": "trace-004",
            "tenant_id": "tenant-123",
            "workflow_id": "workflow-456",
            "capability_key": "email.send",
        }

        # Act
        with collector.start_trace(context) as trace:
            # Simulate execution
            time.sleep(0.01)
            trace.set_decision("Policy allowed")
            trace.set_success()

        # Assert
        assert collector.store.persist.called
        saved_trace = collector.store.persist.call_args[0][0]
        assert saved_trace.trace_id == "trace-004"
        assert saved_trace.outcome == TraceOutcome.SUCCESS
        assert saved_trace.latency_ms >= 10  # At least 10ms

    def test_unhappy_collector_tracks_fallback(self, collector):
        """Unhappy 1: collector tracks fallback usage"""
        # Arrange
        context = {
            "trace_id": "trace-005",
            "tenant_id": "tenant-123",
            "workflow_id": "workflow-456",
            "capability_key": "email.send",
            "primary_provider": "sendgrid",
            "fallback_provider": "aws_ses",
        }

        # Act
        with collector.start_trace(context) as trace:
            trace.set_decision("Primary failed, using fallback")
            trace.set_fallback_used("sendgrid", "aws_ses")
            trace.set_success()

        # Assert
        saved_trace = collector.store.persist.call_args[0][0]
        assert saved_trace.fallback_used is True
        assert saved_trace.primary_provider == "sendgrid"
        assert saved_trace.fallback_provider == "aws_ses"

    def test_unhappy_collector_captures_failure_details(self, collector):
        """Unhappy 2: collector captures failure details"""
        # Arrange
        context = {
            "trace_id": "trace-006",
            "tenant_id": "tenant-123",
            "workflow_id": "workflow-456",
            "capability_key": "payment.charge",
        }

        error = Exception("Payment failed")

        # Act
        try:
            with collector.start_trace(context) as trace:
                trace.set_decision("Execution started")
                raise error
        except:
            pass  # Expected

        # Assert
        saved_trace = collector.store.persist.call_args[0][0]
        assert saved_trace.outcome == TraceOutcome.FAILED
        assert saved_trace.error_message is not None


class TestTraceStore:
    """Tests for trace persistence"""

    def test_happy_trace_persisted_to_store(self):
        """Happy: trace is persisted and retrievable"""
        # Arrange
        store = TraceStore()
        trace = ExecutionTrace(
            trace_id="trace-007",
            tenant_id="tenant-123",
            workflow_id="workflow-456",
            capability_key="email.send",
            outcome=TraceOutcome.SUCCESS,
            latency_ms=100,
        )

        # Act
        store.persist(trace)
        retrieved = store.get_by_trace_id("trace-007")

        # Assert
        assert retrieved is not None
        assert retrieved.trace_id == "trace-007"
        assert retrieved.tenant_id == "tenant-123"

    def test_happy_query_traces_by_tenant_and_workflow(self):
        """Happy: can query traces by tenant and workflow"""
        # Arrange
        store = TraceStore()

        # Store multiple traces
        for i in range(3):
            store.persist(
                ExecutionTrace(
                    trace_id=f"trace-{i}",
                    tenant_id="tenant-123",
                    workflow_id="workflow-456",
                    capability_key="email.send",
                    outcome=TraceOutcome.SUCCESS,
                    latency_ms=100,
                )
            )

        # Different tenant
        store.persist(
            ExecutionTrace(
                trace_id="trace-other",
                tenant_id="tenant-999",
                workflow_id="workflow-456",
                capability_key="email.send",
                outcome=TraceOutcome.SUCCESS,
                latency_ms=100,
            )
        )

        # Act
        traces = store.query(tenant_id="tenant-123", workflow_id="workflow-456")

        # Assert
        assert len(traces) == 3
        assert all(t.tenant_id == "tenant-123" for t in traces)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
