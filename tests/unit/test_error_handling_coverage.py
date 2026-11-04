"""
Comprehensive tests for src/core/api/error_handling.py
Coverage target: 100% of error handling module
"""

from datetime import datetime

import pytest
from fastapi import HTTPException

from src.core.api.error_handling import (
    ERROR_TEMPLATES,
    ErrorDiagnostics,
    get_template_error,
    handle_endpoint_error,
)


class TestErrorDiagnostics:
    """Test ErrorDiagnostics class"""

    def test_analyze_import_error(self):
        """Test analysis of import/module errors"""
        # Arrange
        error = ImportError("No module named 'missing_module'")

        # Act
        result = ErrorDiagnostics.analyze_error(error, "test_context")

        # Assert
        assert result["category"] == "dependency_error"
        assert result["status_code"] == 503
        assert "dependency" in result["error"].lower()
        assert "missing_module" in result["message"]
        assert len(result["troubleshooting"]) > 0
        assert result["error_type"] == "ImportError"

    def test_analyze_module_not_found_error(self):
        """Test analysis of module not found errors"""
        # Arrange
        error = ModuleNotFoundError("No module named 'test'")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "dependency_error"
        assert "module" in result["message"].lower()

    def test_analyze_attribute_error(self):
        """Test analysis of attribute errors (missing imports)"""
        # Arrange
        error = AttributeError("module 'test' has no attribute 'func'")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "dependency_error"
        assert result["status_code"] == 503

    def test_analyze_connection_error(self):
        """Test analysis of connection/timeout errors"""
        # Arrange
        error = ConnectionError("Database connection failed")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "connectivity_error"
        assert result["status_code"] == 503
        assert "connectivity" in result["error"].lower()
        assert any("database" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_timeout_error(self):
        """Test analysis of timeout errors"""
        # Arrange
        error = Exception("Request timeout - connection timed out")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "connectivity_error"
        assert "timeout" in result["message"].lower()

    def test_analyze_database_error(self):
        """Test analysis of database errors"""
        # Arrange
        error = Exception("Database pool exhausted")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "connectivity_error"
        assert any("pool" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_permission_error(self):
        """Test analysis of permission errors"""
        # Arrange
        error = PermissionError("Access denied to resource")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "access_error"
        assert result["status_code"] == 403
        assert "permission" in result["error"].lower()
        assert any("permission" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_access_error(self):
        """Test analysis of access denied errors"""
        # Arrange
        error = Exception("Access forbidden to this resource")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "access_error"
        assert result["status_code"] == 403

    def test_analyze_unauthorized_error(self):
        """Test analysis of unauthorized errors"""
        # Arrange
        error = Exception("Unauthorized access attempt")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "access_error"
        assert any("authentication" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_validation_error(self):
        """Test analysis of validation/input errors"""
        # Arrange
        error = ValueError("Invalid input format")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "validation_error"
        assert result["status_code"] == 400
        assert "validation" in result["error"].lower()
        assert any("input" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_parse_error(self):
        """Test analysis of parsing errors"""
        # Arrange
        error = Exception("Failed to parse JSON data")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "validation_error"
        assert "parse" in result["message"].lower()

    def test_analyze_resource_memory_error(self):
        """Test analysis of memory/resource errors"""
        # Arrange
        error = MemoryError("Out of memory")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "resource_error"
        assert result["status_code"] == 507
        assert "resource" in result["error"].lower()
        assert any("memory" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_quota_exceeded_error(self):
        """Test analysis of quota exceeded errors"""
        # Arrange
        error = Exception("Quota limit exceeded")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "resource_error"
        assert "quota" in result["message"].lower()

    def test_analyze_configuration_error(self):
        """Test analysis of configuration errors"""
        # Arrange
        error = Exception("Configuration file not found")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "configuration_error"
        assert result["status_code"] == 500
        assert "configuration" in result["error"].lower()
        assert any("environment" in tip.lower() for tip in result["troubleshooting"])

    def test_analyze_environment_variable_error(self):
        """Test analysis of environment variable errors"""
        # Arrange
        error = Exception("Required environment variable not set")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "configuration_error"
        assert "variable" in result["message"].lower()

    def test_analyze_generic_server_error(self):
        """Test analysis of generic/unknown errors"""
        # Arrange
        error = Exception("Something unexpected happened")

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert result["category"] == "server_error"
        assert result["status_code"] == 500
        assert "internal server error" in result["error"].lower()
        assert len(result["troubleshooting"]) > 0

    def test_analyze_error_message_truncation(self):
        """Test error message is truncated to 200 chars"""
        # Arrange
        long_message = "x" * 500
        error = Exception(long_message)

        # Act
        result = ErrorDiagnostics.analyze_error(error)

        # Assert
        assert len(result["message"]) <= 250  # "prefix: " + 200 chars


class TestCreateHttpException:
    """Test ErrorDiagnostics.create_http_exception method"""

    def test_create_http_exception_basic(self):
        """Test creating HTTPException from error"""
        # Arrange
        error = ImportError("Missing module")

        # Act
        exc = ErrorDiagnostics.create_http_exception(error, "test endpoint")

        # Assert
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 503  # dependency error
        assert "error" in exc.detail
        assert "message" in exc.detail
        assert "troubleshooting" in exc.detail
        assert "timestamp" in exc.detail

    def test_create_http_exception_with_context(self):
        """Test HTTPException includes context"""
        # Arrange
        error = ValueError("Invalid data")
        context = "user registration endpoint"

        # Act
        exc = ErrorDiagnostics.create_http_exception(error, context)

        # Assert
        assert exc.detail["context"] == context
        assert exc.status_code == 400  # validation error

    def test_create_http_exception_without_context(self):
        """Test HTTPException without context"""
        # Arrange
        error = ConnectionError("Database down")

        # Act
        exc = ErrorDiagnostics.create_http_exception(error)

        # Assert
        assert "context" not in exc.detail
        assert exc.status_code == 503

    def test_create_http_exception_timestamp_format(self):
        """Test timestamp is in ISO format"""
        # Arrange
        error = Exception("Test error")

        # Act
        exc = ErrorDiagnostics.create_http_exception(error)

        # Assert
        timestamp = exc.detail["timestamp"]
        # Should be parseable as ISO datetime
        datetime.fromisoformat(timestamp)

    def test_create_http_exception_includes_error_type(self):
        """Test exception detail includes error type"""
        # Arrange
        error = KeyError("missing_key")

        # Act
        exc = ErrorDiagnostics.create_http_exception(error)

        # Assert
        assert exc.detail["error_type"] == "KeyError"

    def test_create_http_exception_includes_category(self):
        """Test exception detail includes category"""
        # Arrange
        error = PermissionError("Access denied")

        # Act
        exc = ErrorDiagnostics.create_http_exception(error)

        # Assert
        assert exc.detail["category"] == "access_error"

    def test_create_http_exception_logging(self, caplog):
        """Test error is logged when HTTPException is created"""
        # Arrange
        import logging

        caplog.set_level(logging.ERROR)

        error = Exception("Test error for logging")
        context = "test context"

        # Act
        ErrorDiagnostics.create_http_exception(error, context)

        # Assert
        assert any("test error for logging" in record.message.lower() for record in caplog.records)
        assert any("test context" in record.message.lower() for record in caplog.records)


class TestHandleEndpointError:
    """Test handle_endpoint_error function"""

    def test_handle_endpoint_error_basic(self):
        """Test handling endpoint error"""
        # Arrange
        error = ValueError("Invalid input")
        endpoint_name = "create_user"

        # Act
        exc = handle_endpoint_error(error, endpoint_name)

        # Assert
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 400
        assert "create_user endpoint" in exc.detail["context"]

    def test_handle_endpoint_error_preserves_diagnostics(self):
        """Test endpoint error preserves full diagnostics"""
        # Arrange
        error = ConnectionError("Database connection failed")
        endpoint_name = "list_agents"

        # Act
        exc = handle_endpoint_error(error, endpoint_name)

        # Assert
        assert "troubleshooting" in exc.detail
        assert "error_type" in exc.detail
        assert "category" in exc.detail
        assert exc.detail["category"] == "connectivity_error"


class TestErrorTemplates:
    """Test ERROR_TEMPLATES dictionary"""

    def test_error_templates_exist(self):
        """Test predefined error templates exist"""
        # Assert
        assert "agent_not_found" in ERROR_TEMPLATES
        assert "template_not_found" in ERROR_TEMPLATES
        assert "service_unavailable" in ERROR_TEMPLATES

    def test_agent_not_found_template(self):
        """Test agent_not_found template"""
        # Act
        template = ERROR_TEMPLATES["agent_not_found"]

        # Assert
        assert "error" in template
        assert "troubleshooting" in template
        assert len(template["troubleshooting"]) > 0
        assert "agent" in template["error"].lower()

    def test_template_not_found_template(self):
        """Test template_not_found template"""
        # Act
        template = ERROR_TEMPLATES["template_not_found"]

        # Assert
        assert "template" in template["error"].lower()
        assert any("GET /templates" in tip for tip in template["troubleshooting"])

    def test_service_unavailable_template(self):
        """Test service_unavailable template"""
        # Act
        template = ERROR_TEMPLATES["service_unavailable"]

        # Assert
        assert "unavailable" in template["error"].lower()
        assert len(template["troubleshooting"]) >= 3


class TestGetTemplateError:
    """Test get_template_error function"""

    def test_get_template_error_basic(self):
        """Test getting a predefined error template"""
        # Act
        result = get_template_error("agent_not_found")

        # Assert
        assert "error" in result
        assert "troubleshooting" in result
        assert "timestamp" in result
        # Timestamp should be parseable
        datetime.fromisoformat(result["timestamp"])

    def test_get_template_error_with_kwargs(self):
        """Test getting template with custom values"""
        # Act
        result = get_template_error("agent_not_found", agent_id="agent-123", user_id="user-456")

        # Assert
        assert result["agent_id"] == "agent-123"
        assert result["user_id"] == "user-456"
        assert "error" in result
        assert "troubleshooting" in result

    def test_get_template_error_unknown_template(self):
        """Test getting unknown template returns empty dict with timestamp"""
        # Act
        result = get_template_error("unknown_template")

        # Assert
        assert "timestamp" in result
        # Should return empty template + timestamp
        assert len(result) == 1  # Only timestamp

    def test_get_template_error_preserves_template(self):
        """Test getting template doesn't modify original"""
        # Arrange
        original_template = ERROR_TEMPLATES["agent_not_found"].copy()

        # Act
        result = get_template_error("agent_not_found", custom_field="value")

        # Assert
        assert "custom_field" not in ERROR_TEMPLATES["agent_not_found"]
        assert ERROR_TEMPLATES["agent_not_found"] == original_template

    def test_get_template_error_timestamp_format(self):
        """Test timestamp is in correct ISO format"""
        # Act
        result = get_template_error("service_unavailable")

        # Assert
        timestamp = result["timestamp"]
        # Should be valid ISO format
        parsed = datetime.fromisoformat(timestamp)
        assert isinstance(parsed, datetime)
