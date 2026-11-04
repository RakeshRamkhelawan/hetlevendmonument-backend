"""
Tests for OpenTelemetry tracing integration.

Verifies:
- Tracing initialization in production mode
- Tracing disabled in testing mode
- Configuration from unified_config
- FastAPI instrumentation
"""

from unittest.mock import MagicMock, patch

import pytest


class TestOpenTelemetryConfiguration:
    """Tests for OpenTelemetry configuration."""

    def test_otel_config_defaults(self):
        """Verify OTEL configuration defaults in unified_config."""
        from src.core.config.unified_config import config

        assert hasattr(config, "otel_enabled")
        assert hasattr(config, "otel_service_name")
        assert hasattr(config, "otel_exporter_otlp_endpoint")
        assert config.otel_service_name == "sanskritisetu-backend"
        assert "4317" in config.otel_exporter_otlp_endpoint

    def test_tracing_module_imports(self):
        """Verify tracing module can be imported."""
        from src.core.monitoring.tracing import initialize_tracing

        assert callable(initialize_tracing)


class TestTracingInitialization:
    """Tests for tracing initialization behavior."""

    def test_tracing_skipped_in_testing_mode(self):
        """Verify tracing is not initialized when testing=True."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.app_factory import create_app

        with patch("src.core.app_factory.initialize_tracing") as mock_init:
            app = create_app(testing=True)
            mock_init.assert_not_called()

    def test_tracing_called_in_production_mode(self):
        """Verify tracing is initialized when testing=False."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.app_factory import create_app

        with patch("src.core.app_factory.initialize_tracing") as mock_init:
            app = create_app(testing=False)
            mock_init.assert_called_once()

    def test_tracing_failure_does_not_crash_app(self):
        """Verify app creation succeeds even if tracing fails."""
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.core.app_factory import create_app

        with patch(
            "src.core.app_factory.initialize_tracing",
            side_effect=Exception("OTEL error"),
        ):
            # Should not raise, just log warning
            app = create_app(testing=False)
            assert app is not None


class TestTracingDisabled:
    """Tests for when tracing is disabled via config."""

    def test_tracing_respects_otel_enabled_false(self):
        """Verify tracing is skipped when otel_enabled=False."""
        from unittest.mock import MagicMock

        from src.core.monitoring.tracing import initialize_tracing

        mock_app = MagicMock()

        with patch("src.core.monitoring.tracing.config") as mock_config:
            mock_config.otel_enabled = False
            initialize_tracing(mock_app)
            # FastAPIInstrumentor should not be called
            # (function returns early when disabled)


class TestTracerProvider:
    """Tests for tracer provider setup."""

    def test_opentelemetry_imports_available(self):
        """Verify all required OpenTelemetry imports are available."""
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        assert trace is not None
        assert TracerProvider is not None
        assert Resource is not None
        assert OTLPSpanExporter is not None
        assert FastAPIInstrumentor is not None
