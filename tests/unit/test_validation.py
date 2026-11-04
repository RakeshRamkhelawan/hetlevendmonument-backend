"""Tests for validation error formatting."""

import pytest

from src.core.exceptions.validation import format_validation_errors


class TestValidationErrors:
    """Test validation error formatting."""

    @pytest.mark.unit
    def test_format_validation_errors_with_missing_field(self):
        """format_validation_errors must format missing field errors."""
        errors = [
            {
                "loc": ("body", "email"),
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]
        result = format_validation_errors(errors)

        assert len(result) == 1
        assert result[0]["field"] == "email"
        assert result[0]["error"] == "This field is required"

    @pytest.mark.unit
    def test_format_validation_errors_with_type_error(self):
        """format_validation_errors must format type errors."""
        errors = [
            {
                "loc": ("body", "age"),
                "msg": "value is not a valid integer",
                "type": "type_error.integer",
            }
        ]
        result = format_validation_errors(errors)

        assert len(result) == 1
        assert result[0]["field"] == "age"
        assert "Invalid type" in result[0]["error"]

    @pytest.mark.unit
    def test_format_validation_errors_with_value_error(self):
        """format_validation_errors must format value errors."""
        errors = [
            {
                "loc": ("body", "status"),
                "msg": "value_error.invalid_status",
                "type": "value_error",
            }
        ]
        result = format_validation_errors(errors)

        assert len(result) == 1
        assert result[0]["field"] == "status"
        assert result[0]["error"] == "invalid_status"

    @pytest.mark.unit
    def test_format_validation_errors_with_nested_field(self):
        """format_validation_errors must format nested field errors."""
        errors = [
            {
                "loc": ("body", "address", "street"),
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]
        result = format_validation_errors(errors)

        assert len(result) == 1
        assert result[0]["field"] == "address.street"

    @pytest.mark.unit
    def test_format_validation_errors_returns_list_of_dicts(self):
        """format_validation_errors must return list[dict[str, str]]."""
        errors = [{"loc": ("body", "field"), "msg": "error", "type": "value_error"}]
        result = format_validation_errors(errors)

        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert isinstance(item, dict)
            assert "field" in item
            assert "error" in item

    @pytest.mark.unit
    def test_format_validation_errors_with_empty_loc(self):
        """format_validation_errors must handle empty location."""
        errors = [{"loc": [], "msg": "error", "type": "value_error"}]
        result = format_validation_errors(errors)

        assert len(result) == 1
        assert result[0]["field"] == "request"

    @pytest.mark.unit
    def test_format_validation_errors_with_multiple_errors(self):
        """format_validation_errors must format multiple errors."""
        errors = [
            {
                "loc": ("body", "email"),
                "msg": "field required",
                "type": "value_error.missing",
            },
            {
                "loc": ("body", "age"),
                "msg": "value is not a valid integer",
                "type": "type_error.integer",
            },
        ]
        result = format_validation_errors(errors)

        assert len(result) == 2
        assert result[0]["field"] == "email"
        assert result[1]["field"] == "age"
