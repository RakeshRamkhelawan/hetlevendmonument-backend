"""Tests for input sanitization and injection protection."""

import pytest
from pydantic import BaseModel, ValidationError

from src.core.security.input_sanitization import (
    SecureIntField,
    SecureStringField,
    validate_integer_id,
    validate_search_query,
    validate_string_input,
)


class TestSecureStringFieldPydantic:
    """Test SecureStringField as Pydantic v2 field type."""

    @pytest.mark.unit
    def test_secure_string_field_validates_safe_input(self):
        """SecureStringField must work as Pydantic v2 field type for safe input."""

        class TestModel(BaseModel):
            name: SecureStringField

        model = TestModel(name="safe user input")
        assert model.name == "safe user input"
        assert isinstance(model.name, str)

    @pytest.mark.unit
    def test_secure_string_field_rejects_sql_injection(self):
        """SecureStringField must reject SQL injection with ValidationError."""

        class TestModel(BaseModel):
            name: SecureStringField

        with pytest.raises(ValidationError) as exc_info:
            TestModel(name="'; DROP TABLE users; --")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert "name" in str(errors).lower()

    @pytest.mark.unit
    def test_secure_string_field_rejects_union_select_injection(self):
        """SecureStringField must reject UNION SELECT injection."""

        class TestModel(BaseModel):
            query: SecureStringField

        with pytest.raises(ValidationError) as exc_info:
            TestModel(query="1 UNION SELECT * FROM users--")

        errors = exc_info.value.errors()
        assert len(errors) > 0

    @pytest.mark.unit
    def test_secure_string_field_user_sees_validation_error(self):
        """User who enters SQL injection sees validation error, not silent failure."""

        class TestModel(BaseModel):
            input_field: SecureStringField

        with pytest.raises(ValidationError) as exc_info:
            TestModel(input_field="admin' OR '1'='1")

        errors = exc_info.value.errors()
        assert len(errors) > 0
        assert "validation error" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_secure_string_field_rejects_non_string(self):
        """SecureStringField must reject non-string types."""

        class TestModel(BaseModel):
            name: SecureStringField

        with pytest.raises(ValidationError):
            TestModel(name=123)

    @pytest.mark.unit
    def test_secure_string_field_multiple_fields_in_model(self):
        """Multiple SecureStringField instances in one model work correctly."""

        class TestModel(BaseModel):
            field1: SecureStringField
            field2: SecureStringField

        model = TestModel(field1="safe1", field2="safe2")
        assert model.field1 == "safe1"
        assert model.field2 == "safe2"

    @pytest.mark.unit
    def test_secure_string_field_mixed_with_regular_fields(self):
        """SecureStringField works alongside regular string fields."""

        class TestModel(BaseModel):
            secure: SecureStringField
            regular: str

        model = TestModel(secure="safe", regular="anything")
        assert model.secure == "safe"
        assert model.regular == "anything"


class TestSecureIntFieldPydantic:
    """Test SecureIntField as Pydantic v2 field type."""

    @pytest.mark.unit
    def test_secure_int_field_accepts_valid_integer(self):
        """SecureIntField must accept valid positive integers."""

        class TestModel(BaseModel):
            tenant_id: SecureIntField

        model = TestModel(tenant_id=42)
        assert model.tenant_id == 42
        assert isinstance(model.tenant_id, int)

    @pytest.mark.unit
    def test_secure_int_field_coerces_numeric_string(self):
        """SecureIntField must coerce numeric strings to int."""

        class TestModel(BaseModel):
            id_field: SecureIntField

        model = TestModel(id_field="123")
        assert model.id_field == 123

    @pytest.mark.unit
    def test_secure_int_field_rejects_non_numeric_string(self):
        """SecureIntField must reject non-numeric strings."""

        class TestModel(BaseModel):
            id_field: SecureIntField

        with pytest.raises(ValidationError):
            TestModel(id_field="not_a_number")

    @pytest.mark.unit
    def test_secure_int_field_rejects_sql_injection_string(self):
        """SecureIntField must reject SQL injection via string coercion."""

        class TestModel(BaseModel):
            id_field: SecureIntField

        with pytest.raises(ValidationError):
            TestModel(id_field="1 OR 1=1")

    @pytest.mark.unit
    def test_secure_int_field_enforces_bounds(self):
        """SecureIntField must enforce min/max bounds."""

        class TestModel(BaseModel):
            id_field: SecureIntField

        # Should accept valid range
        model = TestModel(id_field=1)
        assert model.id_field == 1

        # Should reject out of range (max is 2147483647 by default)
        with pytest.raises(ValidationError):
            TestModel(id_field=2147483648)

    @pytest.mark.unit
    def test_secure_int_field_rejects_bool(self):
        """SecureIntField must reject boolean values (which are ints in Python)."""

        class TestModel(BaseModel):
            id_field: SecureIntField

        with pytest.raises(ValidationError):
            TestModel(id_field=True)

    @pytest.mark.unit
    def test_secure_int_field_rejects_none(self):
        """SecureIntField must reject None values."""

        class TestModel(BaseModel):
            id_field: SecureIntField

        with pytest.raises(ValidationError):
            TestModel(id_field=None)


class TestValidateStringInput:
    """Test validate_string_input convenience function."""

    @pytest.mark.unit
    def test_validate_string_input_accepts_safe_string(self):
        """validate_string_input must accept safe strings."""
        result = validate_string_input("hello world")
        assert result == "hello world"

    @pytest.mark.unit
    def test_validate_string_input_rejects_sql_injection(self):
        """validate_string_input must reject SQL injection patterns."""
        with pytest.raises(ValueError) as exc_info:
            validate_string_input("'; DROP TABLE users; --")

        assert "input" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_validate_string_input_strips_whitespace(self):
        """validate_string_input must strip leading/trailing whitespace by default."""
        result = validate_string_input("  hello  ")
        assert result == "hello"

    @pytest.mark.unit
    def test_validate_string_input_enforces_max_length(self):
        """validate_string_input must enforce max_length."""
        with pytest.raises(ValueError):
            validate_string_input("x" * 1001, max_length=1000)

    @pytest.mark.unit
    def test_validate_string_input_allows_empty_when_configured(self):
        """validate_string_input must allow empty strings when allow_empty=True."""
        result = validate_string_input("", allow_empty=True)
        assert result == ""


class TestValidateIntegerId:
    """Test validate_integer_id convenience function."""

    @pytest.mark.unit
    def test_validate_integer_id_accepts_valid_int(self):
        """validate_integer_id must accept valid positive integers."""
        result = validate_integer_id(42)
        assert result == 42

    @pytest.mark.unit
    def test_validate_integer_id_coerces_numeric_string(self):
        """validate_integer_id must coerce numeric strings."""
        result = validate_integer_id("123")
        assert result == 123

    @pytest.mark.unit
    def test_validate_integer_id_rejects_sql_injection_string(self):
        """validate_integer_id must reject SQL injection via string."""
        with pytest.raises(ValueError) as exc_info:
            validate_integer_id("1 OR 1=1")

        assert "sql injection" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_validate_integer_id_rejects_bool(self):
        """validate_integer_id must reject boolean values."""
        with pytest.raises(ValueError):
            validate_integer_id(True)

    @pytest.mark.unit
    def test_validate_integer_id_rejects_none(self):
        """validate_integer_id must reject None."""
        with pytest.raises(ValueError):
            validate_integer_id(None)


class TestValidateSearchQuery:
    """Test validate_search_query convenience function."""

    @pytest.mark.unit
    def test_validate_search_query_accepts_safe_query(self):
        """validate_search_query must accept safe search terms."""
        result = validate_search_query("python programming")
        assert result == "python programming"

    @pytest.mark.unit
    def test_validate_search_query_rejects_sql_injection(self):
        """validate_search_query must reject SQL injection in search."""
        with pytest.raises(ValueError):
            validate_search_query("'; DROP TABLE users; --")

    @pytest.mark.unit
    def test_validate_search_query_allows_empty(self):
        """validate_search_query must allow empty search by default."""
        result = validate_search_query("")
        assert result == ""

    @pytest.mark.unit
    def test_validate_search_query_rejects_encoding_evasion(self):
        """validate_search_query must reject URL-encoded evasion attempts."""
        with pytest.raises(ValueError):
            validate_search_query("test%27OR%271%27%3D%271")
