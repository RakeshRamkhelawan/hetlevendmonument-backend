"""Legacy Phase-0 trace compatibility layer.

Provides TraceOutcome, TraceCollector and TraceStore APIs expected by
older integration tests.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import cast, Any, Dict, List, Optional


class TraceOutcome(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING_APPROVAL = "pending_approval"


@dataclass
class LegacyExecutionTrace:
    trace_id: str
    tenant_id: str
    workflow_id: str
    capability_key: str
    timestamp: datetime
    decision_reason: str = ""
    approval_state: str = "not_required"
    fallback_used: bool = False
    primary_provider: str | None = None
    fallback_provider: str | None = None
    outcome: TraceOutcome = TraceOutcome.SUCCESS
    latency_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    error_context: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def is_success(self) -> bool:
        return self.outcome == TraceOutcome.SUCCESS


class TraceStore:
    """Sync in-memory store used by legacy phase-0 tests."""

    def __init__(self) -> None:
        self._traces: list[LegacyExecutionTrace] = []

    def persist(self, trace: LegacyExecutionTrace) -> None:
        self._traces.append(trace)

    def get_workflow_traces(self, workflow_id: str) -> list[LegacyExecutionTrace]:
        return [t for t in self._traces if t.workflow_id == workflow_id]

    def get_stats(self) -> dict[str, int]:
        return {"total_traces": len(self._traces)}


class _TraceBuilder:
    def __init__(self, context: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        self.trace_id = context.get("trace_id", f"trace-{uuid.uuid4().hex[:8]}")
        self.tenant_id = context["tenant_id"]
        self.workflow_id = context["workflow_id"]
        self.capability_key = context["capability_key"]
        self.decision_reason = ""
        self.approval_state = "not_required"
        self.fallback_used = False
        self.primary_provider: str | None = None
        self.fallback_provider: str | None = None
        self.outcome = TraceOutcome.SUCCESS
        self.error_code: str | None = None
        self.error_message: str | None = None
        self.error_context: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.metadata: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self._start = time.time()

    def set_decision(self, reason: str) -> None:
        self.decision_reason = reason

    def set_approval_state(self, state: str) -> None:
        self.approval_state = state

    def set_fallback_used(self, primary: str, fallback: str) -> None:
        self.fallback_used = True
        self.primary_provider = primary
        self.fallback_provider = fallback

    def set_success(self) -> None:
        self.outcome = TraceOutcome.SUCCESS

    def set_failure(
        self, error_code: str, error_message: str, error_context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        self.outcome = TraceOutcome.FAILED
        self.error_code = error_code
        self.error_message = error_message
        self.error_context = error_context or {}

    def set_pending_approval(self) -> None:
        self.outcome = TraceOutcome.PENDING_APPROVAL
        self.approval_state = "pending"

    def build(self) -> LegacyExecutionTrace:
        return LegacyExecutionTrace(
            trace_id=self.trace_id,
            tenant_id=self.tenant_id,
            workflow_id=self.workflow_id,
            capability_key=self.capability_key,
            timestamp=datetime.now(timezone.utc),
            decision_reason=self.decision_reason,
            approval_state=self.approval_state,
            fallback_used=self.fallback_used,
            primary_provider=self.primary_provider,
            fallback_provider=self.fallback_provider,
            outcome=self.outcome,
            latency_ms=max(0, int((time.time() - self._start) * 1000)),
            error_code=self.error_code,
            error_message=self.error_message,
            error_context=self.error_context,
            metadata=self.metadata,
        )


class TraceCollector:
    """Legacy trace collector with context-manager API."""

    def __init__(self, store: TraceStore) -> None:
        self.store = store
        self._active: dict[str, _TraceBuilder] = {}

    @contextmanager
    def start_trace(self, context: dict[str, Any]) -> Any:  # TODO(TYPE): replace Any with concrete type
        builder = _TraceBuilder(context)
        self._active[builder.trace_id] = builder
        try:
            yield builder
        except Exception as exc:
            builder.set_failure(
                type(exc).__name__, str(exc), {"exception_type": type(exc).__name__}
            )
            raise
        finally:
            trace = builder.build()
            # Support both legacy TraceStore (persist) and new TraceStore (save)
            if hasattr(self.store, "persist"):
                try:
                    self.store.persist(trace)
                except (NotImplementedError, AttributeError):
                    # persist exists but is not implemented or is abstract
                    # Store in memory for retrieval
                    if not hasattr(self.store, "_legacy_traces"):
                        self.store._legacy_traces = []  # type: ignore[attr-defined]
                    self.store._legacy_traces.append(trace)  # type: ignore[attr-defined]
            elif hasattr(self.store, "save"):
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    # We're in async context - schedule the save
                    if not hasattr(self.store, "_pending"):
                        self.store._pending = []  # type: ignore[attr-defined]
                    self.store._pending.append(trace)  # type: ignore[attr-defined]
                except RuntimeError:
                    # No running loop - create one
                    try:
                        asyncio.run(cast(Any, self.store).save(trace))  # TODO(TYPE): replace Any with concrete type
                    except NotImplementedError:
                        # save is abstract/not implemented - store in memory
                        if not hasattr(self.store, "_legacy_traces"):
                            self.store._legacy_traces = []  # type: ignore[attr-defined]
                        self.store._legacy_traces.append(trace)  # type: ignore[attr-defined]
            else:
                # Neither persist nor save - store in memory as fallback
                if not hasattr(self.store, "_legacy_traces"):
                    self.store._legacy_traces = []  # type: ignore[attr-defined]
                self.store._legacy_traces.append(trace)  # type: ignore[attr-defined]
            self._active.pop(builder.trace_id, None)
