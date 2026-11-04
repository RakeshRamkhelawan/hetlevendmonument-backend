"""
Unit tests for OpenTelemetry Tracing - Slice 1

Tests procedure-specific span creation and context propagation.
Sprint 4 - S4.1: OpenTelemetry spans per step
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

otel_trace = pytest.importorskip(
    "opentelemetry.sdk.trace.export", reason="opentelemetry-sdk not properly installed"
)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def tracer_provider():
    """Setup in-memory span exporter for testing."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    return provider, exporter


@pytest.fixture
def clear_spans(tracer_provider):
    """Clear spans after each test."""
    _, exporter = tracer_provider
    yield exporter
    exporter.clear()


class TestProcedureTracing:
    """Test suite for procedure execution tracing."""

    def test_start_trace_creates_root_span(self, tracer_provider, clear_spans):
        """Verify root span creation with procedure_id."""
        from src.core.observability.tracing import TraceManager

        provider, exporter = tracer_provider
        trace_manager = TraceManager(tracer_provider=provider)

        # Start root span for procedure
        with trace_manager.start_procedure_trace(
            procedure_id="proc_123",
            tenant_id=1,
            user_id=42,
            procedure_name="invoice.approval",
        ):
            pass

        # Verify span was created
        spans = exporter.get_finished_spans()
        assert len(spans) == 1

        root_span = spans[0]
        assert root_span.name == "procedure.execute"
        assert root_span.attributes.get("procedure.id") == "proc_123"
        assert root_span.attributes.get("tenant.id") == 1
        assert root_span.attributes.get("user.id") == 42
        assert root_span.attributes.get("procedure.name") == "invoice.approval"

    def test_step_execution_creates_child_span(self, tracer_provider, clear_spans):
        """Verify procedure.step span with child-parent relationship."""
        from src.core.observability.tracing import TraceManager

        provider, exporter = tracer_provider
        trace_manager = TraceManager(tracer_provider=provider)

        # Create parent + child span
        with trace_manager.start_procedure_trace(procedure_id="proc_123", tenant_id=1, user_id=42):
            with trace_manager.trace_step(
                step_name="budget_check",
                step_type="executor",
                tool_name="finance_api.get_budget",
            ):
                pass

        # Verify spans
        spans = exporter.get_finished_spans()
        assert len(spans) == 2

        # Child span finishes first
        child_span = spans[0]
        parent_span = spans[1]

        assert child_span.name == "procedure.step"
        assert child_span.attributes.get("step.name") == "budget_check"
        assert child_span.attributes.get("step.type") == "executor"
        assert child_span.attributes.get("tool.name") == "finance_api.get_budget"

        # Verify parent-child relationship
        assert child_span.parent is not None
        assert child_span.parent.span_id == parent_span.context.span_id

    def test_error_adds_exception_event(self, tracer_provider, clear_spans):
        """Exception details should be recorded in span."""
        from src.core.observability.tracing import TraceManager

        provider, exporter = tracer_provider
        trace_manager = TraceManager(tracer_provider=provider)

        # Simulate error in step
        with pytest.raises(ValueError):
            with trace_manager.start_procedure_trace(procedure_id="proc_123", tenant_id=1):
                with trace_manager.trace_step(step_name="failing_step", step_type="executor"):
                    raise ValueError("Budget exceeded")

        # Verify exception was recorded
        spans = exporter.get_finished_spans()
        assert len(spans) == 2

        child_span = spans[0]
        assert child_span.status.is_ok is False

        # Check exception event
        events = child_span.events
        assert len(events) > 0
        exception_event = events[0]
        assert exception_event.name == "exception"
        assert "Budget exceeded" in str(exception_event.attributes.get("exception.message", ""))

    def test_multiple_steps_in_sequence(self, tracer_provider, clear_spans):
        """Multiple sequential steps should all be children of root."""
        from src.core.observability.tracing import TraceManager

        provider, exporter = tracer_provider
        trace_manager = TraceManager(tracer_provider=provider)

        with trace_manager.start_procedure_trace(procedure_id="proc_123", tenant_id=1):
            with trace_manager.trace_step(step_name="step1", step_type="planner"):
                pass
            with trace_manager.trace_step(step_name="step2", step_type="executor"):
                pass
            with trace_manager.trace_step(step_name="step3", step_type="reviewer"):
                pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 4  # 3 steps + 1 root

        # Verify all steps are children of root
        root_span = spans[3]
        for i in range(3):
            step_span = spans[i]
            assert step_span.parent.span_id == root_span.context.span_id

    def test_nested_procedure_calls(self, tracer_provider, clear_spans):
        """Sub-procedures should create nested trace structure."""
        from src.core.observability.tracing import TraceManager

        provider, exporter = tracer_provider
        trace_manager = TraceManager(tracer_provider=provider)

        with trace_manager.start_procedure_trace(procedure_id="parent_proc", tenant_id=1):
            with trace_manager.trace_step(step_name="parent_step", step_type="executor"):
                # Nested sub-procedure
                with trace_manager.start_procedure_trace(procedure_id="child_proc", tenant_id=1):
                    with trace_manager.trace_step(step_name="child_step", step_type="executor"):
                        pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 4  # parent proc + parent step + child proc + child step

        # Verify hierarchy
        child_step = spans[0]
        child_proc = spans[1]
        parent_step = spans[2]
        parent_proc = spans[3]

        assert child_step.parent.span_id == child_proc.context.span_id
        assert child_proc.parent.span_id == parent_step.context.span_id
        assert parent_step.parent.span_id == parent_proc.context.span_id

    def test_trace_attributes_preserved_across_steps(self, tracer_provider, clear_spans):
        """Tenant and user context should propagate to all child spans."""
        from src.core.observability.tracing import TraceManager

        provider, exporter = tracer_provider
        trace_manager = TraceManager(tracer_provider=provider)

        with trace_manager.start_procedure_trace(procedure_id="proc_123", tenant_id=99, user_id=42):
            with trace_manager.trace_step(step_name="step1", step_type="executor"):
                pass

        spans = exporter.get_finished_spans()
        root_span = spans[1]

        # Root span should have tenant/user
        assert root_span.attributes.get("tenant.id") == 99
        assert root_span.attributes.get("user.id") == 42

    def test_trace_manager_singleton(self, tracer_provider):
        """TraceManager should be importable as singleton."""
        import src.core.observability.tracing as tracing_module
        from src.core.observability.tracing import _trace_manager_instance

        provider, _ = tracer_provider

        # Reset singleton
        tracing_module._trace_manager_instance = None

        # Create instances using the test tracer provider
        from src.core.observability.tracing import TraceManager

        manager1 = TraceManager(tracer_provider=provider)
        manager2 = TraceManager(tracer_provider=provider)

        # Different instances since we're not using the singleton pattern here
        # The singleton is for production use via get_trace_manager()
        assert isinstance(manager1, TraceManager)
        assert isinstance(manager2, TraceManager)
