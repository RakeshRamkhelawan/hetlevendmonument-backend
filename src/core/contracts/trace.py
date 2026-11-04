"""
Execution Trace Contract

Implementeert execution tracing voor observability, debugging en audit.
Elke workflow execution genereert een trace met spans voor elke node execution.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set


class SpanStatus(str, Enum):
    """Status van een execution span."""

    PENDING = "pending"  # Nog niet gestart
    RUNNING = "running"  # Bezig
    SUCCESS = "success"  # Succesvol afgerond
    FAILED = "failed"  # Gefaald
    CANCELLED = "cancelled"  # Geannuleerd
    SKIPPED = "skipped"  # Overgeslagen (bijv. conditional)
    PENDING_APPROVAL = "pending_approval"  # Wacht op approval
    TIMEOUT = "timeout"  # Timeout


class SpanType(str, Enum):
    """Type van een execution span."""

    WORKFLOW = "workflow"  # Root workflow span
    NODE = "node"  # Individual node execution
    CAPABILITY = "capability"  # Capability execution
    RETRY = "retry"  # Retry attempt
    FALLBACK = "fallback"  # Fallback execution
    APPROVAL = "approval"  # Approval step


@dataclass(frozen=True)
class TraceContext:
    """
    Context die doorgegeven wordt tussen spans.

    Bevat correlation IDs voor distributed tracing.
    """

    trace_id: str
    parent_span_id: str | None = None
    tenant_id: str | None = None
    workflow_id: str | None = None
    execution_id: str | None = None
    user_id: str | None = None
    correlation_id: str | None = None

    def child_context(self, span_id: str) -> "TraceContext":
        """Create child context voor een sub-span."""
        return TraceContext(
            trace_id=self.trace_id,
            parent_span_id=span_id,
            tenant_id=self.tenant_id,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            user_id=self.user_id,
            correlation_id=self.correlation_id,
        )

    def to_headers(self) -> dict[str, str]:
        """Convert naar HTTP headers voor distributed tracing."""
        headers = {"X-Trace-ID": self.trace_id}
        if self.parent_span_id:
            headers["X-Parent-Span-ID"] = self.parent_span_id
        if self.correlation_id:
            headers["X-Correlation-ID"] = self.correlation_id
        return headers

    @classmethod
    def from_headers(cls, headers: dict[str, str]) -> "TraceContext":
        """Create context vanuit HTTP headers."""
        return cls(
            trace_id=headers.get("X-Trace-ID", str(uuid.uuid4())),
            parent_span_id=headers.get("X-Parent-Span-ID"),
            correlation_id=headers.get("X-Correlation-ID"),
        )


@dataclass
class SpanEvent:
    """
    Event binnen een span (milestone of significant moment).

    Bijvoorbeeld: "input_validated", "api_called", "response_received"
    """

    name: str
    timestamp: datetime
    attributes: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "attributes": self.attributes,
        }


@dataclass
class ExecutionSpan:
    """
    Een span representeert een unit of work in de execution.

    Dit volgt het OpenTelemetry span model maar is vereenvoudigd
    voor onze use case.
    """

    # Identifiers
    span_id: str
    trace_id: str
    parent_span_id: str | None = None

    # Metadata
    name: str = ""  # Bijvoorbeeld: "payment.process"
    span_type: SpanType = SpanType.NODE
    capability_key: str | None = None  # Als dit een capability execution is

    # Timing
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Status
    status: SpanStatus = SpanStatus.PENDING
    status_message: str | None = None  # Bijvoorbeeld foutmelding

    # Data
    input_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    output_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    # Events (milestones)
    events: list[SpanEvent] = field(default_factory=list)

    # Context
    context: TraceContext = field(default_factory=lambda: TraceContext(trace_id=str(uuid.uuid4())))

    # Additional attributes
    attributes: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    # Retry/fallback info
    retry_attempt: int = 0
    max_retries: int = 0
    is_fallback: bool = False
    fallback_from: str | None = None  # Original capability dat failed

    # Performance metrics
    duration_ms: float | None = None

    def start(self, timestamp: datetime | None = None) -> None:
        """Markeer start van de span."""
        self.start_time = timestamp or datetime.now(timezone.utc)
        self.status = SpanStatus.RUNNING

    def end(
        self,
        status: SpanStatus = SpanStatus.SUCCESS,
        status_message: str | None = None,
        timestamp: datetime | None = None,
    ) -> None:
        """Markeer einde van de span."""
        self.end_time = timestamp or datetime.now(timezone.utc)
        self.status = status
        self.status_message = status_message

        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            self.duration_ms = delta.total_seconds() * 1000

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:  # TODO(TYPE): replace Any with concrete type
        """Voeg een event toe aan de span."""
        event = SpanEvent(
            name=name, timestamp=datetime.now(timezone.utc), attributes=attributes or {}
        )
        self.events.append(event)

    def set_attribute(self, key: str, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set een attribute op de span."""
        self.attributes[key] = value

    def set_input(self, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set input data (gesanitiseerd)."""
        # TODO: PII filtering gebaseerd op audit policy
        self.input_data = self._sanitize_data(data)

    def set_output(self, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set output data (gesanitiseerd)."""
        self.output_data = self._sanitize_data(data)

    def _sanitize_data(self, data: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Sanitiseer data voor logging (remove PII)."""
        # Basic implementatie - in productie zou dit geconfigureerd worden
        # via de audit policy van de capability
        pii_fields = {"password", "token", "secret", "credit_card", "ssn"}
        sanitized: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for key, value in data.items():
            if any(pii in key.lower() for pii in pii_fields):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = value
        return sanitized

    def is_success(self) -> bool:
        """Check of de span succesvol was."""
        return self.status == SpanStatus.SUCCESS

    def is_failed(self) -> bool:
        """Check of de span gefaald is."""
        return self.status == SpanStatus.FAILED

    def is_complete(self) -> bool:
        """Check of de span compleet is (success, failed, cancelled, etc.)."""
        return self.status in {
            SpanStatus.SUCCESS,
            SpanStatus.FAILED,
            SpanStatus.CANCELLED,
            SpanStatus.SKIPPED,
            SpanStatus.TIMEOUT,
        }

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize span naar dictionary."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "span_type": self.span_type.value,
            "capability_key": self.capability_key,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "status": self.status.value,
            "status_message": self.status_message,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "events": [e.to_dict() for e in self.events],
            "attributes": self.attributes,
            "retry_attempt": self.retry_attempt,
            "is_fallback": self.is_fallback,
        }


@dataclass
class ExecutionTrace:
    """
    Een complete execution trace bevat alle spans voor een workflow execution.

    Dit is het root object dat opgeslagen wordt voor debugging en audit.
    """

    trace_id: str
    tenant_id: str
    workflow_id: str
    execution_id: str

    # Timing
    start_time: datetime
    end_time: datetime | None = None

    # Status
    status: SpanStatus = SpanStatus.PENDING

    # Spans (alle spans in deze trace)
    spans: list[ExecutionSpan] = field(default_factory=list)

    # Root span (de workflow span)
    root_span_id: str | None = None

    # Context
    user_id: str | None = None
    correlation_id: str | None = None

    # Metadata
    attributes: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def add_span(self, span: ExecutionSpan) -> ExecutionSpan:
        """Voeg een span toe aan de trace."""
        self.spans.append(span)
        return span

    def create_span(
        self,
        name: str,
        span_type: SpanType = SpanType.NODE,
        parent_span_id: str | None = None,
        capability_key: str | None = None,
    ) -> ExecutionSpan:
        """Create en voeg een nieuwe span toe."""
        span_id = str(uuid.uuid4())
        span = ExecutionSpan(
            span_id=span_id,
            trace_id=self.trace_id,
            parent_span_id=parent_span_id or self.root_span_id,
            name=name,
            span_type=span_type,
            capability_key=capability_key,
            context=TraceContext(
                trace_id=self.trace_id,
                parent_span_id=parent_span_id or self.root_span_id,
                tenant_id=self.tenant_id,
                workflow_id=self.workflow_id,
                execution_id=self.execution_id,
                correlation_id=self.correlation_id,
            ),
        )
        self.spans.append(span)
        return span

    def get_span(self, span_id: str) -> ExecutionSpan | None:
        """Get een span by ID."""
        for span in self.spans:
            if span.span_id == span_id:
                return span
        return None

    def get_root_span(self) -> ExecutionSpan | None:
        """Get de root span."""
        if self.root_span_id:
            return self.get_span(self.root_span_id)
        return None

    def get_child_spans(self, parent_span_id: str) -> list[ExecutionSpan]:
        """Get alle child spans van een parent."""
        return [s for s in self.spans if s.parent_span_id == parent_span_id]

    def get_failed_spans(self) -> list[ExecutionSpan]:
        """Get alle gefaalde spans."""
        return [s for s in self.spans if s.is_failed()]

    def get_span_tree(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get spans als boom structuur."""

        def build_tree(span_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
            span = self.get_span(span_id)
            if not span:
                return {}

            children = self.get_child_spans(span_id)
            return {"span": span.to_dict(), "children": [build_tree(c.span_id) for c in children]}

        if self.root_span_id:
            return build_tree(self.root_span_id)
        return {}

    def complete(self, status: SpanStatus = SpanStatus.SUCCESS) -> None:
        """Markeer de trace als compleet."""
        self.end_time = datetime.now(timezone.utc)
        self.status = status

    def get_duration_ms(self) -> float | None:
        """Get totale duration van de trace."""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000
        return None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize trace naar dictionary."""
        return {
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.get_duration_ms(),
            "status": self.status.value,
            "spans": [s.to_dict() for s in self.spans],
            "root_span_id": self.root_span_id,
            "user_id": self.user_id,
            "correlation_id": self.correlation_id,
            "attributes": self.attributes,
        }

    def to_json(self) -> str:
        """Serialize trace naar JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class TraceBuilder:
    """
    Builder voor het construeren van execution traces.

    Maakt het makkelijk om traces te bouwen met fluent API.
    """

    def __init__(
        self,
        tenant_id: str,
        workflow_id: str,
        execution_id: str | None = None,
        user_id: str | None = None,
    ) -> None:
        self.trace_id = str(uuid.uuid4())
        self.execution_id = execution_id or str(uuid.uuid4())
        self.correlation_id = str(uuid.uuid4())

        self.trace = ExecutionTrace(
            trace_id=self.trace_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            execution_id=self.execution_id,
            start_time=datetime.now(timezone.utc),
            user_id=user_id,
            correlation_id=self.correlation_id,
        )

        # Create root span
        root_span = self.trace.create_span(
            name=f"workflow:{workflow_id}",
            span_type=SpanType.WORKFLOW,
        )
        root_span.start()
        self.trace.root_span_id = root_span.span_id

    def start_node_span(
        self, node_id: str, capability_key: str, input_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionSpan:
        """Start een nieuwe node span."""
        span = self.trace.create_span(
            name=f"node:{node_id}",
            span_type=SpanType.NODE,
            parent_span_id=self.trace.root_span_id,
            capability_key=capability_key,
        )
        span.start()
        span.set_attribute("node_id", node_id)

        if input_data:
            span.set_input(input_data)

        return span

    def start_capability_span(
        self,
        capability_key: str,
        parent_span_id: str,
        input_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        retry_attempt: int = 0,
        is_fallback: bool = False,
        fallback_from: str | None = None,
    ) -> ExecutionSpan:
        """Start een capability execution span."""
        span = self.trace.create_span(
            name=capability_key,
            span_type=SpanType.CAPABILITY,
            parent_span_id=parent_span_id,
            capability_key=capability_key,
        )
        span.start()
        span.retry_attempt = retry_attempt
        span.is_fallback = is_fallback
        span.fallback_from = fallback_from

        if input_data:
            span.set_input(input_data)

        return span

    def end_span(
        self,
        span: ExecutionSpan,
        status: SpanStatus = SpanStatus.SUCCESS,
        output_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        status_message: str | None = None,
    ) -> None:
        """Eindig een span."""
        if output_data:
            span.set_output(output_data)
        span.end(status=status, status_message=status_message)

    def complete(self, status: SpanStatus = SpanStatus.SUCCESS) -> ExecutionTrace:
        """Complete de trace en return het resultaat."""
        # End root span
        root_span = self.trace.get_root_span()
        if root_span and not root_span.is_complete():
            root_span.end(status=status)

        self.trace.complete(status=status)
        return self.trace


class TraceStore:
    """
    Abstract base class voor trace persistence.

    Implementaties kunnen opslaan in DB, Elasticsearch, etc.
    """

    async def save(self, trace: ExecutionTrace) -> str:
        """Save een trace. Returns trace ID."""
        raise NotImplementedError

    async def get(self, trace_id: str) -> ExecutionTrace | None:
        """Get een trace by ID."""
        raise NotImplementedError

    async def query(
        self,
        tenant_id: str | None = None,
        workflow_id: str | None = None,
        execution_id: str | None = None,
        status: SpanStatus | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExecutionTrace]:
        """Query traces met filters."""
        raise NotImplementedError

    def get_workflow_traces(self, workflow_id: str) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get traces for a specific workflow (legacy support)."""
        raise NotImplementedError


class InMemoryTraceStore(TraceStore):
    """In-memory implementatie voor testing."""

    def __init__(self) -> None:
        self._traces: dict[str, ExecutionTrace] = {}
        self._legacy_traces: list[Any] = []  # For LegacyExecutionTrace objects  # TODO(TYPE): replace Any with concrete type

    async def save(self, trace: ExecutionTrace) -> str:
        self._traces[trace.trace_id] = trace
        return trace.trace_id

    async def get(self, trace_id: str) -> ExecutionTrace | None:
        return self._traces.get(trace_id)

    async def query(
        self,
        tenant_id: str | None = None,
        workflow_id: str | None = None,
        execution_id: str | None = None,
        status: SpanStatus | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[ExecutionTrace]:
        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for trace in self._traces.values():
            if tenant_id and trace.tenant_id != tenant_id:
                continue
            if workflow_id and trace.workflow_id != workflow_id:
                continue
            if execution_id and trace.execution_id != execution_id:
                continue
            if status and trace.status != status:
                continue
            results.append(trace)
            if len(results) >= limit:
                break
        return results

    def get_workflow_traces(self, workflow_id: str) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Get traces for a specific workflow (legacy support)."""
        # First check in legacy traces
        legacy = [t for t in self._legacy_traces if getattr(t, "workflow_id", None) == workflow_id]
        if legacy:
            return legacy
        # Fall back to regular traces
        return [t for t in self._traces.values() if t.workflow_id == workflow_id]


def create_trace_context(
    tenant_id: str,
    workflow_id: str,
    execution_id: str | None = None,
    user_id: str | None = None,
) -> TraceContext:
    """Factory functie voor het maken van een trace context."""
    return TraceContext(
        trace_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        execution_id=execution_id or str(uuid.uuid4()),
        user_id=user_id,
        correlation_id=str(uuid.uuid4()),
    )
