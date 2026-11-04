"""
Unit Tests for Validation Error Customization (SC-8.1)

Tests custom validation error formatting.
"""

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from src.core.exceptions.validation import format_validation_errors, validation_exception_handler


class TestFormatValidationErrors:
    """Tests for format_validation_errors function."""

    def test_formats_single_error(self):
        """Test formatting single validation error."""
        errors = [{"loc": ["body", "email"], "msg": "Invalid email", "type": "value_error"}]
        formatted = format_validation_errors(errors)

        assert len(formatted) == 1
        assert formatted[0]["field"] == "email"
        assert "Invalid email" in formatted[0]["error"]

    def test_formats_multiple_errors(self):
        """Test formatting multiple validation errors."""
        errors = [
            {"loc": ["body", "email"], "msg": "Invalid", "type": "value_error"},
            {"loc": ["body", "password"], "msg": "Too short", "type": "value_error"},
        ]
        formatted = format_validation_errors(errors)

        assert len(formatted) == 2
        fields = [e["field"] for e in formatted]
        assert "email" in fields
        assert "password" in fields

    def test_missing_field_error(self):
        """Test missing field error message."""
        errors = [
            {
                "loc": ["body", "name"],
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]
        formatted = format_validation_errors(errors)

        assert "required" in formatted[0]["error"]

    def test_nested_field_path(self):
        """Test nested field path formatting."""
        errors = [
            {
                "loc": ["body", "address", "city"],
                "msg": "Invalid",
                "type": "value_error",
            }
        ]
        formatted = format_validation_errors(errors)

        assert formatted[0]["field"] == "address.city"

    def test_empty_errors_list(self):
        """Test empty errors list."""
        formatted = format_validation_errors([])
        assert formatted == []


class TestValidationExceptionHandler:
    """Tests for validation_exception_handler function."""

    @pytest.mark.asyncio
    async def test_returns_422_status(self):
        """Test handler returns 422 status code."""
        from unittest.mock import MagicMock

        request = MagicMock(spec=Request)
        exc = RequestValidationError(
            errors=[{"loc": ["body", "test"], "msg": "Error", "type": "value_error"}]
        )

        response = await validation_exception_handler(request, exc)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_json_response(self):
        """Test handler returns proper JSON structure."""
        import json
        from unittest.mock import MagicMock

        request = MagicMock(spec=Request)
        exc = RequestValidationError(
            errors=[{"loc": ["body", "email"], "msg": "Invalid", "type": "value_error"}]
        )

        response = await validation_exception_handler(request, exc)
        content = json.loads(response.body)

        assert "message" in content
        assert "code" in content
        assert "errors" in content
        assert content["code"] == "VALIDATION_ERROR"
