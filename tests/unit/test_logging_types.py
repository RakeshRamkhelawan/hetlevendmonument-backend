"""
Unit tests for structured logging type annotations.
Tests that type annotations are correct and functional.
"""

import logging
import pytest
from src.core.logging.structured_logging import (
    setup_structured_logging,
    LogContext,
    JSONFormatter,
)


@pytest.mark.unit
class TestJSONFormatter:
    """Test JSONFormatter type safety."""

    def test_init_with_defaults(self) -> None:
        """Should initialize with default parameters."""
        formatter = JSONFormatter()
        assert formatter.include_timestamp is True
        assert formatter.include_level is True
        assert formatter.include_logger is True
        assert formatter.include_path is True
        assert formatter.extra_fields == {}

    def test_init_with_custom_params(self) -> None:
        """Should initialize with custom parameters."""
        extra = {"service_id": "test"}
        formatter = JSONFormatter(
            include_timestamp=False,
            include_level=False,
            include_logger=False,
            include_path=False,
            extra_fields=extra,
        )
        assert formatter.include_timestamp is False
        assert formatter.include_level is False
        assert formatter.include_logger is False
        assert formatter.include_path is False
        assert formatter.extra_fields == extra

    def test_format_returns_json_string(self) -> None:
        """Should format LogRecord as JSON string."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        assert isinstance(result, str)
        assert "Test message" in result
        assert "test.logger" in result


@pytest.mark.unit
class TestSetupStructuredLogging:
    """Test setup_structured_logging type safety."""

    def test_setup_with_defaults(self) -> None:
        """Should accept default parameters."""
        # Should not raise any type errors
        setup_structured_logging()

    def test_setup_with_json_true(self) -> None:
        """Should accept json_output=True."""
        setup_structured_logging(json_output=True)

    def test_setup_with_json_false(self) -> None:
        """Should accept json_output=False."""
        setup_structured_logging(json_output=False)

    def test_setup_with_json_none(self) -> None:
        """Should accept json_output=None for auto-detection."""
        setup_structured_logging(json_output=None)

    def test_setup_with_level(self) -> None:
        """Should accept custom logging level."""
        setup_structured_logging(level="DEBUG")
        setup_structured_logging(level="WARNING")

    def test_setup_with_service_name(self) -> None:
        """Should accept custom service name."""
        setup_structured_logging(service_name="test-service")


@pytest.mark.unit
class TestLogContext:
    """Test LogContext type safety and functionality."""

    def test_init_with_no_args(self) -> None:
        """Should initialize with no keyword arguments."""
        ctx = LogContext()
        assert ctx.extra == {}

    def test_init_with_single_kwarg(self) -> None:
        """Should initialize with a single keyword argument."""
        ctx = LogContext(user_id=123)
        assert ctx.extra == {"user_id": 123}

    def test_init_with_multiple_kwargs(self) -> None:
        """Should initialize with multiple keyword arguments."""
        ctx = LogContext(user_id=123, tenant_id=456, request_id="abc-123")
        assert ctx.extra == {"user_id": 123, "tenant_id": 456, "request_id": "abc-123"}

    def test_context_manager_entry(self) -> None:
        """Should enter context manager successfully."""
        ctx = LogContext(test_key="test_value")
        result = ctx.__enter__()
        assert result is ctx

    def test_context_manager_exit(self) -> None:
        """Should exit context manager successfully."""
        ctx = LogContext(test_key="test_value")
        ctx.__enter__()
        # Should not raise any exceptions
        ctx.__exit__(None, None, None)

    def test_context_manager_with_statement(self) -> None:
        """Should work with Python's with statement."""
        with LogContext(test_key="test_value") as ctx:
            assert isinstance(ctx, LogContext)
            assert ctx.extra == {"test_key": "test_value"}
