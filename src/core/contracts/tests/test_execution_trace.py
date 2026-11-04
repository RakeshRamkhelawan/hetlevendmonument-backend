"""
Tests voor Execution Trace Contract (Fase 0.3)

Happy paths:
- Trace creation en span toevoegen
- Span start/end met timing
- Events toevoegen aan spans
- Trace builder gebruik
- Trace tree navigatie

Unhappy paths:
- Span zonder start
- Invalid parent span ID
- Sanitization van PII data
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from src.core.contracts.trace import (
    ExecutionSpan,
    ExecutionTrace,
    InMemoryTraceStore,
    SpanEvent,
    SpanStatus,
    SpanType,
    TraceBuilder,
    TraceContext,
    create_trace_context,
)


class TestTraceContext:
    """Test TraceContext dataclass."""

    def test_create_trace_context(self) -> None:
        """Happy path: Create context met alle velden."""
        ctx = TraceContext(
            trace_id="trace-123",
            parent_span_id="span-456",
            tenant_id="tenant-789",
            workflow_id="workflow-abc",
            execution_id="exec-def",
            user_id="user-ghi",
            correlation_id="corr-jkl",
        )

        assert ctx.trace_id == "trace-123"
        assert ctx.parent_span_id == "span-456"
        assert ctx.tenant_id == "tenant-789"
        assert ctx.correlation_id == "corr-jkl"

    def test_child_context(self) -> None:
        """Happy path: Create child context."""
        parent = TraceContext(
            trace_id="trace-123",
            tenant_id="tenant-789",
            workflow_id="workflow-abc",
        )

        child = parent.child_context("span-456")

        assert child.trace_id == "trace-123"  # Zelfde trace
        assert child.parent_span_id == "span-456"
        assert child.tenant_id == "tenant-789"  # Overgeerfd
        assert child.workflow_id == "workflow-abc"  # Overgeerfd

    def test_to_headers(self) -> None:
        """Happy path: Convert naar HTTP headers."""
        ctx = TraceContext(
            trace_id="trace-123",
            parent_span_id="span-456",
            correlation_id="corr-789",
        )

        headers = ctx.to_headers()

        assert headers["X-Trace-ID"] == "trace-123"
        assert headers["X-Parent-Span-ID"] == "span-456"
        assert headers["X-Correlation-ID"] == "corr-789"

    def test_from_headers(self) -> None:
        """Happy path: Create vanuit HTTP headers."""
        headers: dict[str, str] = {
            "X-Trace-ID": "trace-123",
            "X-Parent-Span-ID": "span-456",
            "X-Correlation-ID": "corr-789",
        }

        ctx = TraceContext.from_headers(headers)

        assert ctx.trace_id == "trace-123"
        assert ctx.parent_span_id == "span-456"
        assert ctx.correlation_id == "corr-789"

    def test_from_headers_generates_trace_id(self) -> None:
        """Happy path: Genereert trace_id als niet aanwezig."""
        ctx = TraceContext.from_headers({})

        assert ctx.trace_id is not None
        assert len(ctx.trace_id) == 36  # UUID formaat


class TestExecutionSpan:
    """Test ExecutionSpan dataclass."""

    def test_create_span(self) -> None:
        """Happy path: Create span met defaults."""
        span = ExecutionSpan(
            span_id="span-123",
            trace_id="trace-456",
            name="test.span",
            span_type=SpanType.NODE,
        )

        assert span.span_id == "span-123"
        assert span.trace_id == "trace-456"
        assert span.name == "test.span"
        assert span.status == SpanStatus.PENDING
        assert span.events == []

    def test_span_start(self) -> None:
        """Happy path: Start span sets status en timing."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.start()

        assert span.status == SpanStatus.RUNNING
        assert span.start_time is not None

    def test_span_end_success(self) -> None:
        """Happy path: End span met success."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")
        span.start()

        span.end(status=SpanStatus.SUCCESS)

        assert span.status == SpanStatus.SUCCESS
        assert span.end_time is not None
        assert span.duration_ms is not None
        assert span.duration_ms >= 0

    def test_span_end_failure(self) -> None:
        """Happy path: End span met failure."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")
        span.start()

        span.end(status=SpanStatus.FAILED, status_message="Something went wrong")

        assert span.status == SpanStatus.FAILED
        assert span.status_message == "Something went wrong"

    def test_span_end_with_timestamp(self) -> None:
        """Happy path: End span met specifieke timestamp."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")
        span.start()

        end_time = datetime.now(timezone.utc)
        span.end(status=SpanStatus.SUCCESS, timestamp=end_time)

        assert span.end_time == end_time

    def test_add_event(self) -> None:
        """Happy path: Voeg event toe aan span."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.add_event("input_validated", {"valid": True})

        assert len(span.events) == 1
        assert span.events[0].name == "input_validated"
        assert span.events[0].attributes["valid"] is True

    def test_set_attribute(self) -> None:
        """Happy path: Set attributes op span."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.set_attribute("node_id", "node-789")
        span.set_attribute("retry_count", 3)

        assert span.attributes["node_id"] == "node-789"
        assert span.attributes["retry_count"] == 3

    def test_set_input(self) -> None:
        """Happy path: Set input data."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.set_input({"amount": 100, "currency": "EUR"})

        assert span.input_data == {"amount": 100, "currency": "EUR"}

    def test_set_output(self) -> None:
        """Happy path: Set output data."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.set_output({"status": "success", "id": "txn-123"})

        assert span.output_data == {"status": "success", "id": "txn-123"}

    def test_sanitize_data_redacts_password(self) -> None:
        """Happy path: PII fields worden geredacteerd."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.set_input({"username": "john", "password": "secret123", "amount": 100})

        assert span.input_data is not None
        assert span.input_data["username"] == "john"
        assert span.input_data["password"] == "***REDACTED***"
        assert span.input_data["amount"] == 100

    def test_sanitize_data_redacts_token(self) -> None:
        """Happy path: Token fields worden geredacteerd."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        span.set_input(
            {
                "api_token": "abc123",
                "auth_token": "xyz789",
            }
        )

        assert span.input_data is not None
        assert span.input_data["api_token"] == "***REDACTED***"
        assert span.input_data["auth_token"] == "***REDACTED***"

    def test_is_success(self) -> None:
        """Happy path: is_success check."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")
        span.start()

        assert span.is_success() is False

        span.end(status=SpanStatus.SUCCESS)
        assert span.is_success() is True

    def test_is_failed(self) -> None:
        """Happy path: is_failed check."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")
        span.start()
        span.end(status=SpanStatus.FAILED)

        assert span.is_failed() is True

    def test_is_complete(self) -> None:
        """Happy path: is_complete check."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")

        # Pending is niet complete
        assert span.is_complete() is False

        # Running is niet complete
        span.start()
        assert span.is_complete() is False

        # Success is complete
        span.end(status=SpanStatus.SUCCESS)
        assert span.is_complete() is True

    def test_is_complete_cancelled(self) -> None:
        """Happy path: Cancelled is complete."""
        span = ExecutionSpan(span_id="span-123", trace_id="trace-456")
        span.start()
        span.end(status=SpanStatus.CANCELLED)

        assert span.is_complete() is True

    def test_to_dict(self) -> None:
        """Happy path: Serialize span naar dict."""
        span = ExecutionSpan(
            span_id="span-123",
            trace_id="trace-456",
            name="test.span",
            span_type=SpanType.CAPABILITY,
            capability_key="email.send",
            retry_attempt=2,
            is_fallback=True,
        )
        span.start()
        span.end(status=SpanStatus.SUCCESS)

        data = span.to_dict()

        assert data["span_id"] == "span-123"
        assert data["trace_id"] == "trace-456"
        assert data["name"] == "test.span"
        assert data["span_type"] == "capability"
        assert data["capability_key"] == "email.send"
        assert data["status"] == "success"
        assert data["retry_attempt"] == 2
        assert data["is_fallback"] is True


class TestExecutionTrace:
    """Test ExecutionTrace dataclass."""

    def test_create_trace(self) -> None:
        """Happy path: Create trace met verplichte velden."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        assert trace.trace_id == "trace-123"
        assert trace.tenant_id == "tenant-456"
        assert trace.workflow_id == "workflow-789"
        assert trace.execution_id == "exec-abc"
        assert trace.status == SpanStatus.PENDING
        assert trace.spans == []

    def test_add_span(self) -> None:
        """Happy path: Voeg span toe aan trace."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        span = ExecutionSpan(span_id="span-1", trace_id="trace-123")
        trace.add_span(span)

        assert len(trace.spans) == 1
        assert trace.spans[0] == span

    def test_create_span(self) -> None:
        """Happy path: Create span via trace."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        span = trace.create_span(
            name="node:step1",
            span_type=SpanType.NODE,
            capability_key="email.send",
        )

        assert span.name == "node:step1"
        assert span.span_type == SpanType.NODE
        assert span.capability_key == "email.send"
        assert span.trace_id == "trace-123"
        assert span.context.tenant_id == "tenant-456"

    def test_get_span(self) -> None:
        """Happy path: Get span by ID."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        span = trace.create_span(name="test")
        retrieved = trace.get_span(span.span_id)
        assert retrieved is not None
        assert retrieved == span

    def test_get_span_not_found(self) -> None:
        """Happy path: Get non-existent span returns None."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        retrieved = trace.get_span("non-existent")

        assert retrieved is None

    def test_get_child_spans(self) -> None:
        """Happy path: Get child spans."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        parent = trace.create_span(name="parent")
        assert parent.span_id is not None
        child1 = trace.create_span(name="child1", parent_span_id=parent.span_id)
        child2 = trace.create_span(name="child2", parent_span_id=parent.span_id)

        children = trace.get_child_spans(parent.span_id)

        assert len(children) == 2
        assert child1 in children
        assert child2 in children

    def test_get_failed_spans(self) -> None:
        """Happy path: Get failed spans."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        span1 = trace.create_span(name="success")
        span1.start()
        span1.end(status=SpanStatus.SUCCESS)

        span2 = trace.create_span(name="failed")
        span2.start()
        span2.end(status=SpanStatus.FAILED)

        failed = trace.get_failed_spans()

        assert len(failed) == 1
        assert failed[0] == span2

    def test_get_span_tree(self) -> None:
        """Happy path: Get span als boom structuur."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
            root_span_id=None,
        )

        root = trace.create_span(name="root", span_type=SpanType.WORKFLOW)
        trace.root_span_id = root.span_id

        child = trace.create_span(name="child", parent_span_id=root.span_id)
        grandchild = trace.create_span(name="grandchild", parent_span_id=child.span_id)

        tree = trace.get_span_tree()

        assert tree["span"]["name"] == "root"
        assert len(tree["children"]) == 1
        child_tree = tree["children"][0]
        assert child_tree["span"]["name"] == "child"

    def test_complete_trace(self) -> None:
        """Happy path: Complete trace."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        trace.complete(status=SpanStatus.SUCCESS)

        assert trace.status == SpanStatus.SUCCESS
        assert trace.end_time is not None

    def test_get_duration_ms(self) -> None:
        """Happy path: Get trace duration."""
        start = datetime.now(timezone.utc)
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=start,
        )

        trace.complete(status=SpanStatus.SUCCESS)

        duration = trace.get_duration_ms()

        assert duration is not None
        assert duration >= 0

    def test_to_dict(self) -> None:
        """Happy path: Serialize trace naar dict."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        span = trace.create_span(name="test")

        data = trace.to_dict()

        assert data["trace_id"] == "trace-123"
        assert data["tenant_id"] == "tenant-456"
        assert data["workflow_id"] == "workflow-789"
        assert data["spans"] is not None
        assert len(data["spans"]) == 1


class TestTraceBuilder:
    """Test TraceBuilder."""

    def test_builder_creates_trace(self) -> None:
        """Happy path: Builder creeert trace met root span."""
        builder = TraceBuilder(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        assert builder.trace is not None
        assert builder.trace.tenant_id == "tenant-123"
        assert builder.trace.workflow_id == "workflow-456"
        assert builder.trace.root_span_id is not None

    def test_builder_creates_root_span(self) -> None:
        """Happy path: Builder creeert root span automatisch."""
        builder = TraceBuilder(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        root_span = builder.trace.get_root_span()

        assert root_span is not None
        assert root_span.span_type == SpanType.WORKFLOW
        assert root_span.status == SpanStatus.RUNNING

    def test_start_node_span(self) -> None:
        """Happy path: Start node span."""
        builder = TraceBuilder(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        span = builder.start_node_span(
            node_id="node-1",
            capability_key="email.send",
            input_data={"to": "test@test.com"},
        )

        assert span.name == "node:node-1"
        assert span.span_type == SpanType.NODE
        assert span.capability_key == "email.send"
        assert span.attributes["node_id"] == "node-1"
        assert span.input_data == {"to": "test@test.com"}
        assert span.status == SpanStatus.RUNNING

    def test_start_capability_span(self) -> None:
        """Happy path: Start capability span."""
        builder = TraceBuilder(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        root = builder.trace.get_root_span()
        assert root is not None
        root_span_id = root.span_id
        span = builder.start_capability_span(
            capability_key="email.send",
            parent_span_id=root_span_id,
            retry_attempt=1,
            is_fallback=True,
            fallback_from="sms.send",
        )

        assert span.name == "email.send"
        assert span.span_type == SpanType.CAPABILITY
        assert span.parent_span_id == root_span_id
        assert span.retry_attempt == 1
        assert span.is_fallback is True
        assert span.fallback_from == "sms.send"

    def test_end_span(self) -> None:
        """Happy path: End span via builder."""
        builder = TraceBuilder(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        span = builder.start_node_span(
            node_id="node-1",
            capability_key="email.send",
        )

        builder.end_span(
            span,
            status=SpanStatus.SUCCESS,
            output_data={"message_id": "msg-123"},
        )

        assert span.status == SpanStatus.SUCCESS
        assert span.output_data == {"message_id": "msg-123"}
        assert span.duration_ms is not None

    def test_complete_trace(self) -> None:
        """Happy path: Complete trace via builder."""
        builder = TraceBuilder(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        trace = builder.complete(status=SpanStatus.SUCCESS)

        assert trace is not None
        assert trace.status == SpanStatus.SUCCESS
        assert trace.end_time is not None

        root = trace.get_root_span()
        assert root is not None
        assert root.status == SpanStatus.SUCCESS
        assert root.is_complete() is True


class TestInMemoryTraceStore:
    """Test InMemoryTraceStore."""

    @pytest.fixture
    def store(self) -> InMemoryTraceStore:
        return InMemoryTraceStore()

    @pytest.mark.asyncio
    async def test_save_and_get(self, store: InMemoryTraceStore) -> None:
        """Happy path: Save en get trace."""
        trace = ExecutionTrace(
            trace_id="trace-123",
            tenant_id="tenant-456",
            workflow_id="workflow-789",
            execution_id="exec-abc",
            start_time=datetime.now(timezone.utc),
        )

        trace_id = await store.save(trace)
        retrieved = await store.get(trace_id)

        assert trace_id == "trace-123"
        assert retrieved == trace

    @pytest.mark.asyncio
    async def test_get_not_found(self, store: InMemoryTraceStore) -> None:
        """Happy path: Get non-existent trace."""
        retrieved = await store.get("non-existent")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_query_by_tenant(self, store: InMemoryTraceStore) -> None:
        """Happy path: Query traces by tenant."""
        trace1 = ExecutionTrace(
            trace_id="trace-1",
            tenant_id="tenant-a",
            workflow_id="wf-1",
            execution_id="exec-1",
            start_time=datetime.now(timezone.utc),
        )
        trace2 = ExecutionTrace(
            trace_id="trace-2",
            tenant_id="tenant-b",
            workflow_id="wf-2",
            execution_id="exec-2",
            start_time=datetime.now(timezone.utc),
        )

        await store.save(trace1)
        await store.save(trace2)

        results = await store.query(tenant_id="tenant-a")

        assert len(results) == 1
        assert results[0].trace_id == "trace-1"

    @pytest.mark.asyncio
    async def test_query_by_workflow(self, store: InMemoryTraceStore) -> None:
        """Happy path: Query traces by workflow."""
        trace1 = ExecutionTrace(
            trace_id="trace-1",
            tenant_id="tenant-a",
            workflow_id="wf-1",
            execution_id="exec-1",
            start_time=datetime.now(timezone.utc),
        )
        trace2 = ExecutionTrace(
            trace_id="trace-2",
            tenant_id="tenant-a",
            workflow_id="wf-2",
            execution_id="exec-2",
            start_time=datetime.now(timezone.utc),
        )

        await store.save(trace1)
        await store.save(trace2)

        results = await store.query(workflow_id="wf-1")

        assert len(results) == 1
        assert results[0].trace_id == "trace-1"

    @pytest.mark.asyncio
    async def test_query_by_status(self, store: InMemoryTraceStore) -> None:
        """Happy path: Query traces by status."""
        trace1 = ExecutionTrace(
            trace_id="trace-1",
            tenant_id="tenant-a",
            workflow_id="wf-1",
            execution_id="exec-1",
            start_time=datetime.now(timezone.utc),
            status=SpanStatus.SUCCESS,
        )
        trace2 = ExecutionTrace(
            trace_id="trace-2",
            tenant_id="tenant-a",
            workflow_id="wf-2",
            execution_id="exec-2",
            start_time=datetime.now(timezone.utc),
            status=SpanStatus.FAILED,
        )

        await store.save(trace1)
        await store.save(trace2)

        results = await store.query(status=SpanStatus.SUCCESS)

        assert len(results) == 1
        assert results[0].trace_id == "trace-1"

    @pytest.mark.asyncio
    async def test_query_limit(self, store: InMemoryTraceStore) -> None:
        """Happy path: Query met limit."""
        for i in range(10):
            trace = ExecutionTrace(
                trace_id=f"trace-{i}",
                tenant_id="tenant-a",
                workflow_id=f"wf-{i}",
                execution_id=f"exec-{i}",
                start_time=datetime.now(timezone.utc),
            )
            await store.save(trace)

        results = await store.query(tenant_id="tenant-a", limit=5)

        assert len(results) == 5


class TestCreateTraceContext:
    """Test create_trace_context factory functie."""

    def test_create_trace_context(self) -> None:
        """Happy path: Create context met factory."""
        ctx = create_trace_context(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
            execution_id="exec-789",
            user_id="user-abc",
        )

        assert ctx.tenant_id == "tenant-123"
        assert ctx.workflow_id == "workflow-456"
        assert ctx.execution_id == "exec-789"
        assert ctx.user_id == "user-abc"
        assert ctx.trace_id is not None
        assert ctx.correlation_id is not None

    def test_create_trace_context_generates_ids(self) -> None:
        """Happy path: Genereert IDs als niet meegegeven."""
        ctx = create_trace_context(
            tenant_id="tenant-123",
            workflow_id="workflow-456",
        )

        assert ctx.execution_id is not None
        assert len(ctx.execution_id) == 36  # UUID formaat


class TestSpanEvent:
    """Test SpanEvent dataclass."""

    def test_create_event(self) -> None:
        """Happy path: Create event."""
        event = SpanEvent(
            name="input_validated",
            timestamp=datetime.now(timezone.utc),
            attributes={"valid": True, "errors": []},
        )

        assert event.name == "input_validated"
        assert event.attributes["valid"] is True

    def test_event_to_dict(self) -> None:
        """Happy path: Serialize event."""
        now = datetime.now(timezone.utc)
        event = SpanEvent(
            name="input_validated",
            timestamp=now,
            attributes={"valid": True},
        )

        data = event.to_dict()

        assert data["name"] == "input_validated"
        assert data["timestamp"] == now.isoformat()
        assert data["attributes"]["valid"] is True


class TestSpanStatus:
    """Test SpanStatus enum."""

    def test_status_values(self) -> None:
        """Happy path: Status values."""
        assert SpanStatus.PENDING.value == "pending"
        assert SpanStatus.RUNNING.value == "running"
        assert SpanStatus.SUCCESS.value == "success"
        assert SpanStatus.FAILED.value == "failed"
        assert SpanStatus.CANCELLED.value == "cancelled"
        assert SpanStatus.SKIPPED.value == "skipped"
        assert SpanStatus.PENDING_APPROVAL.value == "pending_approval"
        assert SpanStatus.TIMEOUT.value == "timeout"


class TestSpanType:
    """Test SpanType enum."""

    def test_type_values(self) -> None:
        """Happy path: Type values."""
        assert SpanType.WORKFLOW.value == "workflow"
        assert SpanType.NODE.value == "node"
        assert SpanType.CAPABILITY.value == "capability"
        assert SpanType.RETRY.value == "retry"
        assert SpanType.FALLBACK.value == "fallback"
        assert SpanType.APPROVAL.value == "approval"
