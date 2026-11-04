"""
OpenTelemetry Tracing Initialization for the Tool Broker Worker
"""

from typing import Any

from src.core.config.unified_config import config

# Pre-declare as Any so pyright knows they are always bound
_otel_trace: Any = None
_Resource: Any = None
_TracerProvider: Any = None
_OTLPSpanExporter: Any = None
_BatchSpanProcessor: Any = None

# OpenTelemetry tracing (optional) - handle version mismatches gracefully
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
        OTLPSpanExporter as _OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import Resource as _Resource
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor as _BatchSpanProcessor

    HAS_OPENTELEMETRY = True
except (ImportError, TypeError):
    HAS_OPENTELEMETRY = False


def initialize_tool_broker_tracing() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Configure and initialize OpenTelemetry tracing for the tool broker."""
    if not HAS_OPENTELEMETRY:
        print("INFO: OpenTelemetry not available - tracing disabled.")
        return None

    if not config.otel_enabled:
        print("INFO: Tool Broker OpenTelemetry tracing is disabled.")
        return _otel_trace.get_tracer(__name__)

    print("INFO: Initializing Tool Broker OpenTelemetry tracing...")

    service_name = "sanskriti-setu-tool-broker"
    resource = _Resource.create(
        attributes={"service.name": service_name, "service.version": "1.0.0"}
    )

    provider = _TracerProvider(resource=resource)
    _otel_trace.set_tracer_provider(provider)

    otlp_exporter = _OTLPSpanExporter(endpoint=config.otel_exporter_otlp_endpoint, insecure=True)

    span_processor = _BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)

    print(
        f"INFO: Tool Broker OpenTelemetry tracing initialized for service '{service_name}' sending to '{config.otel_exporter_otlp_endpoint}'."
    )

    return _otel_trace.get_tracer(__name__)
