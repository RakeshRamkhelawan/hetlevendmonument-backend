"""
Comprehensive tests for src/core/shared/production_logging.py
Coverage target: 100% of production logging
"""

import logging
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.core.shared.production_logging import (
    SafeLogger,
    log_component_health,
    log_critical_error,
    log_llm_provider_status,
    log_performance_metrics,
    log_startup_validation,
    production_logger,
)


class TestLogStartupValidation:
    """Test log_startup_validation function"""

    def test_log_startup_validation_returns_true(self):
        """Test log_startup_validation returns True"""
        result = log_startup_validation()

        assert result is True


class TestLogComponentHealth:
    """Test log_component_health function"""

    def test_log_component_health_basic(self):
        """Test log_component_health with basic parameters"""
        # Should not raise
        log_component_health("database", "healthy", "Connection OK")

    def test_log_component_health_with_duration(self):
        """Test log_component_health with duration"""
        # Should not raise
        log_component_health("api", "healthy", "Response OK", duration=0.5)

    def test_log_component_health_returns_none(self):
        """Test log_component_health returns None"""
        result = log_component_health("test", "ok", "message")

        assert result is None


class TestLogLLMProviderStatus:
    """Test log_llm_provider_status function"""

    def test_log_llm_provider_status_basic(self):
        """Test log_llm_provider_status with basic parameters"""
        # Should not raise
        log_llm_provider_status("google", "gemini-1.5-flash", "active")

    def test_log_llm_provider_status_with_response_time(self):
        """Test log_llm_provider_status with response time"""
        # Should not raise
        log_llm_provider_status("google", "gemini-pro", "active", response_time=1.5)

    def test_log_llm_provider_status_with_error(self):
        """Test log_llm_provider_status with error message"""
        # Should not raise
        log_llm_provider_status("openai", "gpt-4", "error", error_message="API timeout")

    def test_log_llm_provider_status_returns_none(self):
        """Test log_llm_provider_status returns None"""
        result = log_llm_provider_status("test", "model", "status")

        assert result is None


class TestLogCriticalError:
    """Test log_critical_error function"""

    def test_log_critical_error_basic(self):
        """Test log_critical_error with basic parameters"""
        error = Exception("Test error")

        # Should not raise
        log_critical_error("database_error", error)

    def test_log_critical_error_with_context(self):
        """Test log_critical_error with context"""
        error = ValueError("Invalid value")
        context = {"user_id": 123, "operation": "update"}

        # Should not raise
        log_critical_error("validation_error", error, context=context)

    def test_log_critical_error_returns_none(self):
        """Test log_critical_error returns None"""
        error = RuntimeError("Test")
        result = log_critical_error("error_type", error)

        assert result is None


class TestLogPerformanceMetrics:
    """Test log_performance_metrics function"""

    def test_log_performance_metrics_basic(self):
        """Test log_performance_metrics with basic parameters"""
        # Should not raise
        log_performance_metrics("response_time", 0.5, True)

    def test_log_performance_metrics_with_details(self):
        """Test log_performance_metrics with details"""
        details = {"endpoint": "/api/data", "method": "GET"}

        # Should not raise
        log_performance_metrics("api_latency", 1.2, True, details=details)

    def test_log_performance_metrics_failure(self):
        """Test log_performance_metrics with failure"""
        # Should not raise
        log_performance_metrics("query_time", 5.0, False)

    def test_log_performance_metrics_returns_none(self):
        """Test log_performance_metrics returns None"""
        result = log_performance_metrics("metric", 1.0, True)

        assert result is None


class TestSafeLoggerInitialization:
    """Test SafeLogger initialization"""

    def test_safelogger_initialization(self):
        """Test SafeLogger initialization"""
        logger = SafeLogger("test_logger")

        assert logger.logger.name == "test_logger"
        assert logger.logger.level == logging.INFO

    def test_safelogger_has_handler(self):
        """Test SafeLogger has handler configured"""
        logger = SafeLogger("test_logger2")

        assert len(logger.logger.handlers) > 0

    @patch("logging.getLogger")
    def test_safelogger_avoids_duplicate_handlers(self, mock_get_logger):
        """Test SafeLogger doesn't add duplicate handlers"""
        mock_logger_obj = Mock(spec=logging.Logger)
        mock_logger_obj.handlers = [Mock()]  # Already has handler
        mock_logger_obj.setLevel = Mock()
        mock_get_logger.return_value = mock_logger_obj

        logger = SafeLogger("test")

        # Should not add another handler
        assert len(mock_logger_obj.handlers) == 1


class TestSafeLoggerMethods:
    """Test SafeLogger logging methods"""

    def test_info_method(self):
        """Test SafeLogger info method"""
        logger = SafeLogger("test_info")

        with patch.object(logger.logger, "info") as mock_info:
            logger.info("Test info message")
            mock_info.assert_called_once_with("Test info message")

    def test_warning_method(self):
        """Test SafeLogger warning method"""
        logger = SafeLogger("test_warning")

        with patch.object(logger.logger, "warning") as mock_warning:
            logger.warning("Test warning message")
            mock_warning.assert_called_once_with("Test warning message")

    def test_error_method(self):
        """Test SafeLogger error method"""
        logger = SafeLogger("test_error")

        with patch.object(logger.logger, "error") as mock_error:
            logger.error("Test error message")
            mock_error.assert_called_once_with("Test error message")

    def test_critical_method(self):
        """Test SafeLogger critical method"""
        logger = SafeLogger("test_critical")

        with patch.object(logger.logger, "critical") as mock_critical:
            logger.critical("Test critical message")
            mock_critical.assert_called_once_with("Test critical message")

    def test_debug_method(self):
        """Test SafeLogger debug method"""
        logger = SafeLogger("test_debug")

        with patch.object(logger.logger, "debug") as mock_debug:
            logger.debug("Test debug message")
            mock_debug.assert_called_once_with("Test debug message")


class TestSafeLoggerWithArgs:
    """Test SafeLogger methods with args and kwargs"""

    def test_info_with_args(self):
        """Test SafeLogger info with args"""
        logger = SafeLogger("test")

        with patch.object(logger.logger, "info") as mock_info:
            logger.info("Message: %s", "value")
            mock_info.assert_called_once_with("Message: %s", "value")

    def test_warning_with_kwargs(self):
        """Test SafeLogger warning with kwargs"""
        logger = SafeLogger("test")

        with patch.object(logger.logger, "warning") as mock_warning:
            logger.warning("Warning", extra={"key": "value"})
            mock_warning.assert_called_once_with("Warning", extra={"key": "value"})

    def test_error_with_args_and_kwargs(self):
        """Test SafeLogger error with args and kwargs"""
        logger = SafeLogger("test")

        with patch.object(logger.logger, "error") as mock_error:
            logger.error("Error: %s", "test", exc_info=True)
            mock_error.assert_called_once_with("Error: %s", "test", exc_info=True)


class TestProductionLogger:
    """Test global production_logger instance"""

    def test_production_logger_exists(self):
        """Test production_logger instance exists"""
        assert production_logger is not None
        assert isinstance(production_logger, SafeLogger)

    def test_production_logger_name(self):
        """Test production_logger has correct name"""
        assert production_logger.logger.name == "production"

    def test_production_logger_usable(self):
        """Test production_logger is usable"""
        with patch.object(production_logger.logger, "info") as mock_info:
            production_logger.info("Test message")
            mock_info.assert_called_once_with("Test message")


class TestEdgeCases:
    """Test edge cases"""

    def test_safelogger_empty_name(self):
        """Test SafeLogger with empty name - Python logging converts '' to 'root'"""
        logger = SafeLogger("")

        # Python's logging module converts empty string to 'root'
        assert logger.logger.name == "root"

    def test_safelogger_unicode_in_message(self):
        """Test SafeLogger with Unicode in message"""
        logger = SafeLogger("test")

        with patch.object(logger.logger, "info") as mock_info:
            logger.info("Test ✅ message")
            mock_info.assert_called_once()

    def test_log_component_health_all_none(self):
        """Test log_component_health with None duration"""
        # Should not raise
        log_component_health("comp", "status", "msg", duration=None)

    def test_log_llm_provider_all_optional_params(self):
        """Test log_llm_provider_status with all optional params"""
        # Should not raise
        log_llm_provider_status(
            "provider", "model", "status", response_time=1.0, error_message="error"
        )

    def test_log_critical_error_none_context(self):
        """Test log_critical_error with None context"""
        error = Exception("test")
        # Should not raise
        log_critical_error("type", error, context=None)

    def test_log_performance_metrics_none_details(self):
        """Test log_performance_metrics with None details"""
        # Should not raise
        log_performance_metrics("metric", 1.0, True, details=None)
