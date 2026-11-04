"""
Trace Collector for PRD v3.3 Phase 0.

Provides context manager for collecting execution traces
during workflow execution.
"""

import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional, Set
from collections.abc import Iterator

from .trace import ExecutionTrace, SpanStatus, TraceStore


class TraceBuilder:
    """
    Builder for constructing execution traces.

    Used internally by TraceCollector to build traces
    incrementally during execution.
    """

    def __init__(self, context: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        self.trace_id = context.get("trace_id", str(uuid.uuid4()))
        self.tenant_id = context["tenant_id"]
        self.workflow_id = context["workflow_id"]
        self.capability_key = context["capability_key"]
        self.primary_provider = context.get("primary_provider")
        self.fallback_provider = context.get("fallback_provider")
        self.execution_id = context.get("execution_id", str(uuid.uuid4()))

        self.decision_reason = ""
        self.approval_state = "not_required"
        self.fallback_used = False
        self.outcome = SpanStatus.SUCCESS
        self.error_code: str | None = None
        self.error_message: str | None = None
        self.error_context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

        self._start_time = time.time()

    def set_decision(self, reason: str) -> None:
        """Set the decision reason"""
        self.decision_reason = reason

    def set_approval_state(self, state: str) -> None:
        """Set approval state"""
        self.approval_state = state

    def set_fallback_used(self, primary: str, fallback: str) -> None:
        """Mark that fallback was used"""
        self.fallback_used = True
        self.primary_provider = primary
        self.fallback_provider = fallback

    def set_success(self) -> None:
        """Mark execution as successful"""
        self.outcome = SpanStatus.SUCCESS

    def set_failure(
        self, error_code: str, error_message: str, error_context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Mark execution as failed with error details"""
        self.outcome = SpanStatus.FAILED
        self.error_code = error_code
        self.error_message = error_message
        if error_context:
            self.error_context = error_context

    def set_pending_approval(self) -> None:
        """Mark as pending approval"""
        self.outcome = SpanStatus.PENDING_APPROVAL
        self.approval_state = "pending"

    def add_metadata(self, key: str, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add metadata"""
        self.metadata[key] = value

    def build(self) -> ExecutionTrace:
        """Build the final ExecutionTrace"""
        from datetime import datetime, timezone

        latency_ms = int((time.time() - self._start_time) * 1000)

        # Store collector-specific attributes in metadata
        metadata = dict(self.metadata)
        metadata["collector"] = {
            "capability_key": self.capability_key,
            "decision_reason": self.decision_reason,
            "approval_state": self.approval_state,
            "fallback_used": self.fallback_used,
            "primary_provider": self.primary_provider,
            "fallback_provider": self.fallback_provider,
            "latency_ms": latency_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "error_context": self.error_context,
        }

        trace = ExecutionTrace(
            trace_id=self.trace_id,
            tenant_id=self.tenant_id,
            workflow_id=self.workflow_id,
            execution_id=self.execution_id,
            start_time=datetime.now(timezone.utc),
            status=self.outcome,
            attributes=metadata,
        )
        return trace


class TraceCollector:
    """
    Collects execution traces during workflow execution.

    Usage:
        collector = TraceCollector(store=TraceStore())

        with collector.start_trace({
            "tenant_id": "tenant-123",
            "workflow_id": "workflow-456",
            "capability_key": "email.send"
        }) as trace:
            trace.set_decision("Policy allowed")
            # ... execute capability ...
            trace.set_success()

        # Trace is automatically persisted
    """

    def __init__(self, store: TraceStore) -> None:
        """
        Initialize collector.

        Args:
            store: TraceStore for persisting traces
        """
        self.store = store
        self._active_traces: dict[str, TraceBuilder] = {}

    @contextmanager
    def start_trace(self, context: dict[str, Any]) -> Iterator[TraceBuilder]:  # TODO(TYPE): replace Any with concrete type
        """
        Start a new trace context.

        Args:
            context: Execution context with tenant_id, workflow_id, capability_key

        Yields:
            TraceBuilder for recording trace details
        """
        builder = TraceBuilder(context)
        self._active_traces[builder.trace_id] = builder

        try:
            yield builder
        except Exception as e:
            # Capture exception in trace
            builder.set_failure(
                error_code=type(e).__name__,
                error_message=str(e),
                error_context={"exception_type": type(e).__name__},
            )
            raise
        finally:
            # Persist trace
            trace = builder.build()
            # Note: save() is async, need to handle synchronously in sync context
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule async save if in async context
                    asyncio.create_task(self.store.save(trace))
                else:
                    loop.run_until_complete(self.store.save(trace))
            except RuntimeError:
                # No event loop, create one
                asyncio.run(self.store.save(trace))
            del self._active_traces[builder.trace_id]

    def get_active_trace(self, trace_id: str) -> TraceBuilder | None:
        """Get currently active trace by ID"""
        return self._active_traces.get(trace_id)

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get collector statistics"""
        return {
            "active_traces": len(self._active_traces),
            "store_type": type(self.store).__name__,
        }
