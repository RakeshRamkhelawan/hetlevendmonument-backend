"""
OpenTelemetry span helpers and decorators for SanskritiSetu

De daadwerkelijke OTel-bootstrap (TracerProvider/FastAPIInstrumentor/OTLP-exporter)
gebeurt in src.core.monitoring.tracing.initialize_tracing(), aangeroepen vanuit
create_app(). Dit bestand levert alleen span-utilities die BOVENOP een al
geinitialiseerde tracer-provider werken: TraceManager voor procedure/step-spans,
decorators (traced/trace_agent_execution/trace_db_query), context-propagatie en
sampling-configuratie.

AUDIT-ARCH-2026-07-02 Groep 6: dit bestand bevatte voorheen ook een tweede,
nooit-aangeroepen OTel-bootstrap-functie (setup_tracing) die dezelfde
verantwoordelijkheid als initialize_tracing() dupliceerde. Verwijderd -- zie
tests/architecture/test_tracing_single_implementation.py.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Optional, TypeVar, cast
from collections.abc import Callable, Iterator

from loguru import logger

__all__ = ["traced"]

# Runtime availability flag
HAS_OPENTELEMETRY = False

# Type variable for the opentelemetry trace module
TraceModule: Any = None

# Try to import at runtime (graceful degradation if not available)
try:
    from opentelemetry import trace as trace_module

    HAS_OPENTELEMETRY = True
    TraceModule = trace_module
except ImportError:
    trace_module = None  # type: ignore[assignment]  # NOTE: None sentinel when opentelemetry not installed
    logger.debug("OpenTelemetry not available - tracing disabled")


def get_current_span() -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Get the current active span for adding custom attributes.

    Example:
        span = get_current_span()
        if span:
            span.set_attribute("tenant_id", tenant_id)
            span.set_attribute("user_id", user_id)

    Returns:
        Current span or None
    """
    if not HAS_OPENTELEMETRY or trace_module is None:
        return None
    trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
    return trace_mod.get_current_span()


def add_span_attributes(
    attributes: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """
    Add custom attributes to the current span.

    Context7 Best Practice: Add business context to traces

    Args:
        attributes: dict[str, Any] of attribute key-value pairs  # TODO(TYPE): replace Any with concrete type

    Example:
        add_span_attributes({
            "tenant_id": "123",
            "workflow_id": "wf-456",
            "agent_type": "CVA"
        })
    """
    if not HAS_OPENTELEMETRY:
        return

    span = get_current_span()
    if span is not None:
        # Check if span has the is_recording method before calling
        is_recording = getattr(span, "is_recording", lambda: False)()
        if is_recording:
            for key, value in attributes.items():
                if hasattr(span, "set_attribute"):
                    span.set_attribute(key, str(value))


# ==================== SLICE 1: Procedure-Specific Tracing ====================
# Sprint 4 - S4.1: OpenTelemetry spans per step


class TraceManager:
    """
    Manager for procedure execution tracing.

    Provides context managers for creating hierarchical spans:
    - Root span per procedure execution
    - Child spans per step
    - Automatic context propagation
    - Exception recording

    Sprint 4 - S4.1 Implementation
    """

    def __init__(
        self,
        tracer_provider: Any | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Initialize TraceManager.

        Args:
            tracer_provider: Optional custom TracerProvider (for testing)
        """
        if not HAS_OPENTELEMETRY:
            self._tracer = None
            return

        trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type

        if tracer_provider is not None:
            # Tests may run with OTEL_SDK_DISABLED=true globally; explicit providers
            # should still be able to emit spans to their in-memory exporters.
            if getattr(tracer_provider, "_disabled", False):
                tracer_provider._disabled = False
            self._tracer = tracer_provider.get_tracer("sanskritisetu.procedures")
        else:
            self._tracer = trace_mod.get_tracer("sanskritisetu.procedures")

    @contextmanager
    def start_procedure_trace(
        self,
        procedure_id: str,
        tenant_id: int,
        user_id: int | None = None,
        procedure_name: str | None = None,
        **extra_attributes: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> Iterator[Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Create root span for procedure execution.

        Args:
            procedure_id: Unique procedure execution ID
            tenant_id: Tenant context
            user_id: User who triggered execution
            procedure_name: Human-readable procedure name
            **extra_attributes: Additional span attributes

        Example:
            with trace_manager.start_procedure_trace(
                procedure_id="exec_123",
                tenant_id=1,
                user_id=42,
                procedure_name="invoice.approval"
            ):
                # Execute procedure steps
                pass
        """
        if not HAS_OPENTELEMETRY or self._tracer is None:
            # Yield a mock span (None) when tracing is not available
            yield None
            return

        with self._tracer.start_as_current_span("procedure.execute") as span:
            # Set standard attributes
            span.set_attribute("procedure.id", procedure_id)
            span.set_attribute("tenant.id", tenant_id)

            if user_id is not None:
                span.set_attribute("user.id", user_id)

            if procedure_name:
                span.set_attribute("procedure.name", procedure_name)

            # Add extra attributes
            for key, value in extra_attributes.items():
                span.set_attribute(key, str(value))

            try:
                yield span
            except Exception as e:
                # Record exception in span
                span.record_exception(e)
                trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
                span.set_status(trace_mod.Status(trace_mod.StatusCode.ERROR, str(e)))
                raise

    @contextmanager
    def trace_step(
        self,
        step_name: str,
        step_type: str,
        tool_name: str | None = None,
        **extra_attributes: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> Iterator[Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Create child span for procedure step.

        Must be called within a start_procedure_trace context.

        Args:
            step_name: Step identifier (e.g., "budget_check")
            step_type: Capability type (planner/retriever/executor/compliance/reviewer)
            tool_name: Tool being invoked (if applicable)
            **extra_attributes: Additional span attributes

        Example:
            with trace_manager.trace_step(
                step_name="budget_check",
                step_type="executor",
                tool_name="finance_api.get_budget"
            ):
                # Execute step logic
                result = await tool_broker.execute(...)
        """
        if not HAS_OPENTELEMETRY or self._tracer is None:
            # Yield a mock span (None) when tracing is not available
            yield None
            return

        with self._tracer.start_as_current_span("procedure.step") as span:
            # Set standard attributes
            span.set_attribute("step.name", step_name)
            span.set_attribute("step.type", step_type)

            if tool_name:
                span.set_attribute("tool.name", tool_name)

            # Add extra attributes
            for key, value in extra_attributes.items():
                span.set_attribute(key, str(value))

            try:
                yield span
            except Exception as e:
                # Record exception in span
                span.record_exception(e)
                trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
                span.set_status(trace_mod.Status(trace_mod.StatusCode.ERROR, str(e)))
                raise


# Singleton instance
_trace_manager_instance: TraceManager | None = None


def get_trace_manager() -> TraceManager:
    """
    Get singleton TraceManager instance.

    Returns:
        TraceManager instance
    """
    global _trace_manager_instance
    if _trace_manager_instance is None:
        _trace_manager_instance = TraceManager()
    return _trace_manager_instance


# ==================== SLICE 2: Agent Tracing ====================
# Sprint 4 - S4.2: Agent-level spans for process_task

F = TypeVar("F", bound=Callable[..., Any])  # TODO(TYPE): replace Any with concrete type


def trace_agent_execution(
    agent_id_attr: str = "agent_id",
    tenant_id_attr: str = "tenant_id",
    record_tokens: bool = True,
    record_cost: bool = True,
) -> Callable[[F], F]:
    """
    Decorator to trace agent execution with OpenTelemetry spans.

    Args:
        agent_id_attr: Attribute name for agent ID
        tenant_id_attr: Attribute name for tenant ID
        record_tokens: Whether to record token usage
        record_cost: Whether to record cost metrics

    Example:
        @trace_agent_execution()
        async def process_task(self, task_data):
            # Agent logic here
            pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not HAS_OPENTELEMETRY or trace_module is None:
                # Skip tracing if OpenTelemetry not available
                return await func(*args, **kwargs)

            trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type

            # Get tracer
            tracer = trace_mod.get_tracer("sanskritisetu.agents")

            # Extract agent_id and tenant_id from self or kwargs
            agent_id = "unknown"
            tenant_id = "unknown"

            if args and hasattr(args[0], agent_id_attr):
                agent_id = getattr(args[0], agent_id_attr, "unknown")
            if args and hasattr(args[0], tenant_id_attr):
                tenant_id = getattr(args[0], tenant_id_attr, "unknown")

            # Start span
            with tracer.start_as_current_span("agent.process_task") as span:
                span.set_attribute("agent.id", agent_id)
                span.set_attribute("tenant.id", tenant_id)
                span.set_attribute("agent.operation", func.__name__)

                # Record start time for duration calculation
                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)

                    # Record success
                    span.set_attribute("agent.success", True)
                    span.set_attribute("agent.duration_ms", (time.time() - start_time) * 1000)

                    # Try to extract token/cost info from result
                    if record_tokens and isinstance(result, dict):
                        if "tokens_used" in result:
                            span.set_attribute("agent.tokens.used", result["tokens_used"])
                        if "tokens_input" in result:
                            span.set_attribute("agent.tokens.input", result["tokens_input"])
                        if "tokens_output" in result:
                            span.set_attribute("agent.tokens.output", result["tokens_output"])

                    if record_cost and isinstance(result, dict) and "cost" in result:
                        span.set_attribute("agent.cost", result["cost"])

                    return result

                except Exception as e:
                    # Record error
                    span.set_attribute("agent.success", False)
                    span.set_attribute("agent.error", str(e))
                    span.record_exception(e)
                    span.set_status(trace_mod.Status(trace_mod.StatusCode.ERROR, str(e)))
                    raise

        return async_wrapper  # type: ignore[return-value]

    return decorator


def traced(span_name: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator to trace a function execution with an OpenTelemetry span.

    Args:
        span_name: Optional name for the span. Defaults to the function name.
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not HAS_OPENTELEMETRY or trace_module is None:
                return await func(*args, **kwargs)

            trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
            tracer = trace_mod.get_tracer("sanskritisetu.traced")
            name = span_name or func.__name__

            with tracer.start_as_current_span(name) as span:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace_mod.Status(trace_mod.StatusCode.ERROR, str(e)))
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not HAS_OPENTELEMETRY or trace_module is None:
                return func(*args, **kwargs)

            trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
            tracer = trace_mod.get_tracer("sanskritisetu.traced")
            name = span_name or func.__name__

            with tracer.start_as_current_span(name) as span:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace_mod.Status(trace_mod.StatusCode.ERROR, str(e)))
                    raise

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator


# ==================== SLICE 3: Database Query Tracing ====================

# Slow query threshold (milliseconds)
SLOW_QUERY_THRESHOLD_MS = 200


def trace_db_query(query_name: str = "unnamed_query") -> Callable[[F], F]:
    """
    Decorator to trace database queries with timing.

    Automatically tags slow queries (>200ms).

    Args:
        query_name: Name identifier for the query

    Example:
        @trace_db_query("get_user_by_id")
        async def fetch_user(session, user_id):
            return await session.execute(select(User).where(User.id == user_id))
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            if not HAS_OPENTELEMETRY or trace_module is None:
                # Skip tracing if OpenTelemetry not available
                return await func(*args, **kwargs)

            trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
            tracer = trace_mod.get_tracer("sanskritisetu.database")

            with tracer.start_as_current_span("db.query") as span:
                span.set_attribute("db.query.name", query_name)
                span.set_attribute("db.system", "postgresql")

                start_time = time.time()

                try:
                    result = await func(*args, **kwargs)

                    duration_ms = (time.time() - start_time) * 1000
                    span.set_attribute("db.query.duration_ms", duration_ms)

                    # Tag slow queries
                    if duration_ms > SLOW_QUERY_THRESHOLD_MS:
                        span.set_attribute("db.query.slow", True)
                        span.set_attribute("db.query.slow_threshold_ms", SLOW_QUERY_THRESHOLD_MS)
                        logger.warning(
                            f"Slow query detected: {query_name} took {duration_ms:.2f}ms"
                        )
                    else:
                        span.set_attribute("db.query.slow", False)

                    return result

                except Exception as e:
                    span.set_attribute("db.query.error", str(e))
                    span.record_exception(e)
                    span.set_status(trace_mod.Status(trace_mod.StatusCode.ERROR, str(e)))
                    raise

        return async_wrapper  # type: ignore[return-value]

    return decorator


# ==================== SLICE 4: Trace Context Propagation ====================


def get_trace_context() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get current trace context for propagation to workers.

    Returns: dict[str, Any]ionary with traceparent and other context info  # TODO(TYPE): replace Any with concrete type
    """
    if not HAS_OPENTELEMETRY or trace_module is None:
        return {}

    trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type

    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    propagator = TraceContextTextMapPropagator()
    carrier: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    propagator.inject(carrier)

    # Also include correlation_id if it matches trace_id
    current_span = trace_mod.get_current_span()
    if current_span is not None and hasattr(current_span, "get_span_context"):
        span_context = current_span.get_span_context()
        if span_context is not None and hasattr(span_context, "is_valid"):
            if span_context.is_valid:
                if hasattr(span_context, "trace_id"):
                    carrier["trace_id"] = format(span_context.trace_id, "032x")
                if hasattr(span_context, "span_id"):
                    carrier["span_id"] = format(span_context.span_id, "016x")

    return carrier


def set_trace_context(
    context: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """
    Set trace context from propagated context (in worker).

    Args:
        context: dict[str, Any]ionary with traceparent from get_trace_context  # TODO(TYPE): replace Any with concrete type
    """
    if not HAS_OPENTELEMETRY:
        return

    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    propagator = TraceContextTextMapPropagator()
    ctx = propagator.extract(context)

    # Attach context to current execution
    from opentelemetry.context import attach

    attach(ctx)


def get_tracer(name: str) -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Get an OpenTelemetry tracer by name.

    Returns a NoOp tracer when OpenTelemetry is not available.
    """
    if not HAS_OPENTELEMETRY or trace_module is None:
        # Return a minimal no-op tracer-like object
        class _NoOpTracer:
            def start_as_current_span(
                self, *args: Any, **kwargs: Any  # TODO(TYPE): replace Any with concrete type
            ) -> Any:  # TODO(TYPE): replace Any with concrete type
                class _NoOpSpan:
                    def __init__(self) -> None:
                        self.attributes: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
                        self.exceptions: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                        self.status: Any = None  # TODO(TYPE): replace Any with concrete type
                        self.closed: bool = False

                    def __enter__(self) -> "_NoOpSpan":
                        return self

                    def __exit__(
                        self, *args: Any  # TODO(TYPE): replace Any with concrete type
                    ) -> None:
                        self.closed = True

                    def set_attribute(
                        self, key: str, value: Any  # TODO(TYPE): replace Any with concrete type
                    ) -> None:
                        self.attributes[key] = value

                    def record_exception(
                        self, exc: Any  # TODO(TYPE): replace Any with concrete type
                    ) -> None:
                        self.exceptions.append(exc)

                    def set_status(
                        self, status: Any  # TODO(TYPE): replace Any with concrete type
                    ) -> None:
                        self.status = status

                return _NoOpSpan()

        return _NoOpTracer()

    trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
    return trace_mod.get_tracer(name)


def get_correlation_id() -> str:
    """
    Get correlation ID that matches the current trace ID.

    This ensures correlation_id = trace_id for distributed tracing.

    Returns:
        Correlation ID string (trace ID) or empty string
    """
    if not HAS_OPENTELEMETRY or trace_module is None:
        return ""

    trace_mod = cast(Any, trace_module)  # TODO(TYPE): replace Any with concrete type
    current_span = trace_mod.get_current_span()
    if current_span is not None and hasattr(current_span, "get_span_context"):
        span_context = current_span.get_span_context()
        if span_context is not None and hasattr(span_context, "is_valid"):
            if span_context.is_valid and hasattr(span_context, "trace_id"):
                return format(span_context.trace_id, "032x")

    return ""


# ==================== SLICE 5: Sampling Configuration ====================


def configure_sampling(
    environment: str,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get sampling configuration based on environment.

    Args:
        environment: 'development', 'staging', or 'production'

    Returns:
        Sampling configuration dict
    """
    configs = {
        "development": {
            "type": "always_on",  # 100% sampling
            "description": "All traces captured for debugging",
        },
        "staging": {
            "type": "trace_id_ratio",  # 10% base + errors
            "ratio": 0.1,
            "error_sampling": "always",  # Always sample errors
            "slow_sampling_ms": 2000,  # Always sample slow requests >2s
            "description": "10% base sampling + all errors + slow requests",
        },
        "production": {
            "type": "trace_id_ratio",  # 1% base + errors
            "ratio": 0.01,
            "error_sampling": "always",  # Always sample errors
            "slow_sampling_ms": 2000,  # Always sample slow requests >2s
            "description": "1% base sampling + all errors + slow requests",
        },
    }

    return cast(
        dict[str, Any], configs.get(environment, configs["production"])
    )  # TODO(TYPE): replace Any with concrete type
