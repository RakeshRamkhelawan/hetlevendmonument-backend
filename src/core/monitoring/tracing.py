"""
OpenTelemetry Tracing Initialization
"""


from fastapi import FastAPI

from src.core.config.unified_config import config


def initialize_tracing(app: FastAPI) -> None:
    """Configure and initialize OpenTelemetry tracing for the application."""
    if not config.otel_enabled:
        print("INFO: OpenTelemetry tracing is disabled.")
        return

    # Import lazily to avoid import-time failures/warnings during environments
    # where OpenTelemetry exporters are not fully available.
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import (
            FastAPIInstrumentor,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:
        print(f"WARNING: OpenTelemetry tracing initialization skipped: {exc}")
        return

    print("INFO: Initializing OpenTelemetry tracing...")

    # Create a resource to identify this service.
    resource = Resource.create(
        attributes={
            "service.name": config.otel_service_name,
            "service.version": "1.0.0",  # You can make this dynamic
        }
    )

    # Set up a TracerProvider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Configure the OTLP exporter to send traces to a collector (e.g., Jaeger, Signoz)
    otlp_exporter = OTLPSpanExporter(
        endpoint=config.otel_exporter_otlp_endpoint,
        insecure=True,  # Set to False in production with TLS
    )

    # Use a BatchSpanProcessor to send spans in batches
    span_processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)

    # Instrument the FastAPI application automatically
    FastAPIInstrumentor.instrument_app(app)

    print(
        f"INFO: OpenTelemetry tracing initialized for service '{config.otel_service_name}' sending to '{config.otel_exporter_otlp_endpoint}'."
    )
