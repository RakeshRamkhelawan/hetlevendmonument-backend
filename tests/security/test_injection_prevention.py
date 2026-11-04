"""
Tests for SQL/NoSQL Injection Prevention (OWASP A03:2021)
=========================================================

Comprehensive test suite for input sanitization and injection prevention
as required by P5.1.3 security implementation.

Test Categories:
1. SQL Injection Detection - Various SQL injection patterns
2. NoSQL Injection Detection - MongoDB-style operator injection
3. Command Injection Detection - Shell metacharacter detection
4. Path Traversal Detection - Directory traversal patterns
5. Type Coercion Attacks - Preventing type confusion
6. Input Validation - Length, format, character validation
7. Query Builder Safety - SQLAlchemy query building tests
"""

from typing import Any, Dict

import pytest

from src.core.security.input_sanitization import (
    NOSQL_INJECTION_PATTERNS,
    SQL_INJECTION_PATTERNS,
    InjectionProtector,
    InjectionType,
    ValidationResult,
    escape_like_pattern,
    validate_email,
    validate_integer_id,
    validate_json_data,
    validate_search_query,
    validate_string_input,
    validate_uuid,
)
from src.core.security.query_validation import (
    QueryParams,
    SafeQueryBuilder,
    validate_pagination,
    validate_sort_column,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def protector():
    """Create an InjectionProtector instance."""
    return InjectionProtector(log_detections=False)


@pytest.fixture
def sql_injection_payloads():
    """Common SQL injection attack payloads."""
    return [
        # Comment injection
        "admin'--",
        "1'; DROP TABLE users;--",
        "1 /* inline comment */",
        # Union-based injection
        "' UNION SELECT * FROM users--",
        "' UNION ALL SELECT username, password FROM users--",
        "1 UNION SELECT null, user(), database()--",
        # Boolean-based blind injection
        "' OR '1'='1",
        "' OR 1=1--",
        "admin' AND 1=1--",
        "1' AND '1'='1",
        "1 OR a=a",
        # Time-based blind injection
        "'; SLEEP(5);--",
        "1; WAITFOR DELAY '0:0:5';--",
        "' AND BENCHMARK(10000000, SHA1('test'))--",
        "'; SELECT pg_sleep(5);--",
        # Stacked queries
        "'; DROP TABLE users;--",
        "'; DELETE FROM users;--",
        "'; UPDATE users SET password='hacked';--",
        "'; INSERT INTO users VALUES('hacker');--",
        "'; TRUNCATE TABLE audit_logs;--",
        "'; ALTER TABLE users ADD column hacked varchar(100);--",
        "'; CREATE TABLE evil(id int);--",
        "'; GRANT ALL TO public;--",
        # Error-based injection
        "' AND EXTRACTVALUE(1, CONCAT(0x7e, version()))--",
        "' AND UPDATEXML(1, CONCAT(0x7e, version()), 1)--",
        # Function-based injection
        "' AND CONCAT('a','b')='ab'--",
        "1 AND CHAR(65)='A'--",
        "' AND ASCII('a')=97--",
        "' AND HEX('A')='41'--",
        # Information schema access
        "' UNION SELECT table_name FROM information_schema.tables--",
        "' UNION SELECT system_user()--",
        "' UNION SELECT session_user()--",
        "' UNION SELECT current_user()--",
        # Database-specific
        "'; EXEC xp_cmdshell('dir');--",  # SQL Server
        "'; EXEC sp_executesql 'SELECT 1';--",  # SQL Server
        "1 AND @@VERSION > 0--",
        "' UNION SELECT LOAD_FILE('/etc/passwd')--",  # MySQL
        "' INTO OUTFILE '/tmp/evil.txt'--",  # MySQL
        "' INTO DUMPFILE '/tmp/evil.bin'--",  # MySQL
    ]


@pytest.fixture
def nosql_injection_payloads():
    """MongoDB-style NoSQL injection payloads."""
    return [
        # Operator injection
        '{"$gt": ""}',
        '{"$ne": null}',
        '{"$where": "this.password.length > 0"}',
        '{"username": {"$regex": ".*"}}',
        '{"$or": [{"a": 1}, {"b": 2}]}',
        '{"$and": [{"x": 1}]}',
        '{"$exists": true}',
        '{"field": {"$in": [1, 2, 3]}}',
        '{"field": {"$nin": [1]}}',
        '{"$expr": {"$eq": ["$a", "$b"]}}',
        # JavaScript injection
        "function() { return true; }",
        "this.password",
        "db.users.find({})",
        # Nested operators
        '{"a": {"$gt": {"$lt": 10}}}',
    ]


@pytest.fixture
def safe_inputs():
    """Safe inputs that should pass validation."""
    return [
        "Hello World",
        "John Doe",
        "user@example.com",
        "This is a normal sentence.",
        "Item #123",
        "Price: $99.99",
        "2024-01-15",
        "UUID-1234-5678-90ab",
        "SELECT",
        "select",  # Words alone are fine
        "DROP",
        "drop",  # Words alone are fine
        "Test / Something",  # Single slash is ok
        "A-B-C",  # Dashes without SQL context
        "Hello - World",  # Single dash
    ]


# ============================================================================
# SQL INJECTION TESTS
# ============================================================================


class TestSQLInjectionDetection:
    """Test SQL injection pattern detection."""

    def test_detects_comment_injection(self, protector):
        """Test detection of SQL comment injection."""
        result = protector.check_sql_injection("admin'--")
        assert not result.is_valid
        assert result.injection_type == InjectionType.SQL

    def test_detects_union_injection(self, protector):
        """Test detection of UNION-based injection."""
        result = protector.check_sql_injection("' UNION SELECT * FROM users")
        assert not result.is_valid
        assert result.injection_type == InjectionType.SQL

    def test_detects_boolean_blind_injection(self, protector):
        """Test detection of boolean-based blind injection."""
        payloads = [
            "' OR '1'='1",
            "' OR 1=1--",
            "1 AND 1=1",
        ]
        for payload in payloads:
            result = protector.check_sql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"

    def test_detects_time_based_injection(self, protector):
        """Test detection of time-based injection."""
        payloads = [
            "'; SLEEP(5);",
            "WAITFOR DELAY '0:0:5'",
            "BENCHMARK(1000, SHA1('test'))",
            "pg_sleep(5)",
        ]
        for payload in payloads:
            result = protector.check_sql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"

    def test_detects_stacked_queries(self, protector):
        """Test detection of stacked query injection."""
        payloads = [
            "'; DROP TABLE users;",
            "'; DELETE FROM data;",
            "'; UPDATE users SET admin=true;",
            "'; INSERT INTO logs VALUES('hack');",
        ]
        for payload in payloads:
            result = protector.check_sql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"

    def test_detects_information_schema_access(self, protector):
        """Test detection of information schema access attempts."""
        result = protector.check_sql_injection("UNION SELECT * FROM information_schema.tables")
        assert not result.is_valid

    def test_all_sql_payloads_detected(self, protector, sql_injection_payloads):
        """Test that all known SQL injection payloads are detected."""
        undetected = []
        for payload in sql_injection_payloads:
            result = protector.check_sql_injection(payload)
            if result.is_valid:
                undetected.append(payload)

        assert not undetected, f"Undetected SQL injection payloads: {undetected}"

    def test_safe_inputs_allowed(self, protector, safe_inputs):
        """Test that safe inputs pass SQL injection check."""
        for input_val in safe_inputs:
            result = protector.check_sql_injection(input_val)
            assert result.is_valid, f"False positive on: {input_val}"


# ============================================================================
# NOSQL INJECTION TESTS
# ============================================================================


class TestNoSQLInjectionDetection:
    """Test NoSQL injection pattern detection."""

    def test_detects_operator_injection_string(self, protector):
        """Test detection of MongoDB operator injection in strings."""
        payloads = [
            "$where",
            "$gt",
            "$ne",
            "$regex",
            "$or",
            "$and",
            "$exists",
        ]
        for payload in payloads:
            result = protector.check_nosql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"

    def test_detects_operator_injection_dict(self, protector):
        """Test detection of MongoDB operators in dictionaries."""
        payloads = [
            {"$gt": ""},
            {"$ne": None},
            {"field": {"$in": [1, 2]}},
            {"$or": [{"a": 1}]},
        ]
        for payload in payloads:
            result = protector.check_nosql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"

    def test_detects_nested_operators(self, protector):
        """Test detection of deeply nested operators."""
        payload = {"level1": {"level2": {"$gt": 10}}}
        result = protector.check_nosql_injection(payload)
        assert not result.is_valid

    def test_detects_javascript_injection(self, protector):
        """Test detection of JavaScript injection patterns."""
        payloads = [
            "function() { return true; }",
            "this.password",
            "db.users.find()",
        ]
        for payload in payloads:
            result = protector.check_nosql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"

    def test_safe_dict_allowed(self, protector):
        """Test that safe dictionaries pass validation."""
        safe_dicts = [
            {"name": "John", "age": 30},
            {"email": "user@example.com"},
            {"tags": ["a", "b", "c"]},
            {"nested": {"key": "value"}},
        ]
        for d in safe_dicts:
            result = protector.check_nosql_injection(d)
            assert result.is_valid, f"False positive on: {d}"


# ============================================================================
# TYPE COERCION ATTACK TESTS
# ============================================================================


class TestTypeCoercionAttacks:
    """Test prevention of type confusion/coercion attacks."""

    def test_integer_id_rejects_sql_injection_string(self):
        """Test that SQL injection in ID field is rejected."""
        with pytest.raises(ValueError, match="SQL injection"):
            validate_integer_id("1 OR 1=1--", field_name="tenant_id")

    def test_integer_id_rejects_non_numeric_string(self):
        """Test that non-numeric strings are rejected."""
        with pytest.raises(ValueError, match="Invalid integer format"):
            validate_integer_id("abc", field_name="id")

    def test_integer_id_rejects_none(self):
        """Test that None is rejected."""
        with pytest.raises(ValueError, match="Cannot be None"):
            validate_integer_id(None, field_name="id")

    def test_integer_id_accepts_valid_int(self):
        """Test that valid integers are accepted."""
        assert validate_integer_id(123, field_name="id") == 123
        assert validate_integer_id(1, field_name="id") == 1

    def test_integer_id_accepts_numeric_string(self):
        """Test that numeric strings are safely converted."""
        assert validate_integer_id("123", field_name="id") == 123
        assert validate_integer_id("  456  ", field_name="id") == 456

    def test_integer_id_rejects_negative_when_min_is_positive(self):
        """Test that negative values are rejected when min_value > 0."""
        with pytest.raises(ValueError, match="Must be between"):
            validate_integer_id(-1, field_name="id", min_value=1)

    def test_integer_id_rejects_zero_when_min_is_positive(self):
        """Test that zero is rejected when min_value > 0."""
        with pytest.raises(ValueError, match="Must be between"):
            validate_integer_id(0, field_name="id", min_value=1)

    def test_integer_id_accepts_negative_when_allowed(self):
        """Test that negative values work when allowed."""
        assert validate_integer_id(-5, field_name="id", min_value=-100) == -5

    def test_integer_id_rejects_float(self):
        """Test that floats are rejected."""
        with pytest.raises(TypeError, match="Expected int"):
            validate_integer_id(3.14, field_name="id")

    def test_integer_id_rejects_list(self):
        """Test that lists are rejected."""
        with pytest.raises(TypeError, match="Expected int"):
            validate_integer_id([1, 2, 3], field_name="id")

    def test_integer_id_rejects_dict(self):
        """Test that dicts are rejected."""
        with pytest.raises(TypeError, match="Expected int"):
            validate_integer_id({"$gt": 0}, field_name="id")


# ============================================================================
# STRING INPUT VALIDATION TESTS
# ============================================================================


class TestStringInputValidation:
    """Test string input validation."""

    def test_validates_normal_string(self):
        """Test validation of normal strings."""
        result = validate_string_input("Hello World", field_name="name")
        assert result == "Hello World"

    def test_strips_whitespace(self):
        """Test whitespace stripping."""
        result = validate_string_input("  Hello  ", field_name="name")
        assert result == "Hello"

    def test_rejects_empty_string_by_default(self):
        """Test that empty strings are rejected by default."""
        with pytest.raises(ValueError, match="Cannot be empty"):
            validate_string_input("", field_name="name")

    def test_allows_empty_when_configured(self):
        """Test that empty strings can be allowed."""
        result = validate_string_input("", field_name="name", allow_empty=True)
        assert result == ""

    def test_rejects_none(self):
        """Test that None is rejected."""
        with pytest.raises(ValueError, match="Cannot be None"):
            validate_string_input(None, field_name="name")

    def test_rejects_non_string(self):
        """Test that non-strings are rejected."""
        with pytest.raises(ValueError, match="Expected string"):
            validate_string_input(123, field_name="name")

    def test_enforces_max_length(self):
        """Test maximum length enforcement."""
        with pytest.raises(ValueError, match="Cannot exceed"):
            validate_string_input("a" * 101, field_name="name", max_length=100)

    def test_enforces_min_length(self):
        """Test minimum length enforcement."""
        with pytest.raises(ValueError, match="Must be at least"):
            validate_string_input("ab", field_name="name", min_length=3)

    def test_rejects_sql_injection_in_string(self):
        """Test that SQL injection is detected in strings."""
        with pytest.raises(ValueError, match="malicious"):
            validate_string_input("'; DROP TABLE users;--", field_name="query")


# ============================================================================
# SEARCH QUERY VALIDATION TESTS
# ============================================================================


class TestSearchQueryValidation:
    """Test search query validation."""

    def test_validates_normal_search(self):
        """Test validation of normal search queries."""
        result = validate_search_query("hello world", field_name="search")
        assert result == "hello world"

    def test_allows_empty_search(self):
        """Test that empty searches are allowed."""
        result = validate_search_query("", field_name="search")
        assert result == ""

    def test_rejects_sql_injection_in_search(self):
        """Test SQL injection in search queries."""
        with pytest.raises(ValueError):
            validate_search_query("' OR '1'='1", field_name="search")

    def test_rejects_encoded_patterns(self):
        """Test detection of URL-encoded patterns."""
        with pytest.raises(ValueError, match="encoding"):
            validate_search_query("test%27%20OR", field_name="search")


# ============================================================================
# JSON DATA VALIDATION TESTS
# ============================================================================


class TestJSONDataValidation:
    """Test JSON data validation."""

    def test_validates_safe_json(self):
        """Test validation of safe JSON data."""
        data = {"name": "John", "age": 30, "tags": ["a", "b"]}
        result = validate_json_data(data, field_name="data")
        assert result == data

    def test_rejects_nosql_operator_key(self):
        """Test rejection of NoSQL operator keys."""
        with pytest.raises(ValueError, match="NoSQL operator"):
            validate_json_data({"$gt": 10}, field_name="data")

    def test_rejects_nested_operator(self):
        """Test rejection of nested operators."""
        with pytest.raises(ValueError, match="NoSQL operator"):
            validate_json_data({"field": {"$in": [1, 2]}}, field_name="data")

    def test_enforces_max_depth(self):
        """Test maximum nesting depth."""
        # Build deeply nested dict
        data: Dict[str, Any] = {"level": 1}
        current = data
        for i in range(15):
            current["nested"] = {"level": i + 2}
            current = current["nested"]

        with pytest.raises(ValueError, match="nesting exceeds"):
            validate_json_data(data, field_name="data", max_depth=10)

    def test_enforces_max_keys(self):
        """Test maximum key count."""
        data = {f"key_{i}": i for i in range(150)}

        with pytest.raises(ValueError, match="too many keys"):
            validate_json_data(data, field_name="data", max_keys=100)

    def test_rejects_non_dict(self):
        """Test that non-dicts are rejected."""
        with pytest.raises(ValueError, match="Expected dictionary"):
            validate_json_data([1, 2, 3], field_name="data")


# ============================================================================
# EMAIL VALIDATION TESTS
# ============================================================================


class TestEmailValidation:
    """Test email validation."""

    def test_validates_normal_email(self):
        """Test validation of normal emails."""
        result = validate_email("user@example.com", field_name="email")
        assert result == "user@example.com"

    def test_lowercases_email(self):
        """Test that emails are lowercased."""
        result = validate_email("User@Example.COM", field_name="email")
        assert result == "user@example.com"

    def test_rejects_invalid_format(self):
        """Test rejection of invalid email formats."""
        invalid_emails = [
            "not-an-email",
            "@example.com",
            "user@",
            "user@.com",
            "user example.com",
        ]
        for email in invalid_emails:
            with pytest.raises(ValueError, match="Invalid email format"):
                validate_email(email, field_name="email")

    def test_rejects_sql_injection_in_email(self):
        """Test SQL injection in email field."""
        with pytest.raises(ValueError):
            validate_email("user@example.com' OR '1'='1", field_name="email")


# ============================================================================
# UUID VALIDATION TESTS
# ============================================================================


class TestUUIDValidation:
    """Test UUID validation."""

    def test_validates_normal_uuid(self):
        """Test validation of normal UUIDs."""
        result = validate_uuid("550e8400-e29b-41d4-a716-446655440000", field_name="uuid")
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_lowercases_uuid(self):
        """Test that UUIDs are lowercased."""
        result = validate_uuid("550E8400-E29B-41D4-A716-446655440000", field_name="uuid")
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_rejects_invalid_format(self):
        """Test rejection of invalid UUID formats."""
        invalid_uuids = [
            "not-a-uuid",
            "550e8400-e29b-41d4-a716",  # Too short
            "550e8400e29b41d4a716446655440000",  # No dashes
        ]
        for uuid_str in invalid_uuids:
            with pytest.raises(ValueError):  # Can be format or length error
                validate_uuid(uuid_str, field_name="uuid")

        # Test too long separately - will hit length limit first
        with pytest.raises(ValueError, match="exceed"):
            validate_uuid("550e8400-e29b-41d4-a716-446655440000-extra", field_name="uuid")


# ============================================================================
# LIKE PATTERN ESCAPING TESTS
# ============================================================================


class TestLikePatternEscaping:
    """Test LIKE pattern special character escaping."""

    def test_escapes_percent(self):
        """Test escaping of % character."""
        result = escape_like_pattern("100%")
        assert result == "100\\%"

    def test_escapes_underscore(self):
        """Test escaping of _ character."""
        result = escape_like_pattern("hello_world")
        assert result == "hello\\_world"

    def test_escapes_backslash(self):
        """Test escaping of \\ character."""
        result = escape_like_pattern("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_escapes_multiple(self):
        """Test escaping of multiple special characters."""
        result = escape_like_pattern("100% off_sale\\end")
        assert result == "100\\% off\\_sale\\\\end"


# ============================================================================
# QUERY PARAMS VALIDATION TESTS
# ============================================================================


class TestQueryParamsValidation:
    """Test QueryParams validation."""

    def test_validates_pagination(self):
        """Test pagination parameter validation."""
        params = QueryParams(page=2, page_size=50)
        assert params.page == 2
        assert params.page_size == 50
        assert params.offset == 50

    def test_enforces_max_page_size(self):
        """Test maximum page size enforcement."""
        params = QueryParams(page_size=500, max_page_size=100)
        assert params.page_size == 100

    def test_handles_invalid_page(self):
        """Test handling of invalid page numbers."""
        params = QueryParams(page=-1)
        assert params.page == 1

    def test_validates_sort_column(self):
        """Test sort column validation."""
        params = QueryParams(
            sort_by="name",
            allowed_sort_columns={"name", "created_at"},
        )
        assert params.sort_by == "name"

    def test_uses_default_sort_for_invalid(self):
        """Test default sort column for invalid input."""
        params = QueryParams(
            sort_by="invalid_column",
            allowed_sort_columns={"name", "created_at"},
            default_sort_column="created_at",
        )
        assert params.sort_by == "created_at"

    def test_validates_sort_order(self):
        """Test sort order validation."""
        params = QueryParams(sort_order="desc")
        assert params.sort_order == "desc"
        assert params.descending is True

    def test_defaults_invalid_sort_order(self):
        """Test default for invalid sort order."""
        params = QueryParams(sort_order="invalid")
        assert params.sort_order == "asc"
        assert params.descending is False


# ============================================================================
# PAGINATION VALIDATION TESTS
# ============================================================================


class TestPaginationValidation:
    """Test pagination validation function."""

    def test_normal_pagination(self):
        """Test normal pagination values."""
        page, page_size, offset = validate_pagination(page=3, page_size=20)
        assert page == 3
        assert page_size == 20
        assert offset == 40

    def test_handles_invalid_page(self):
        """Test handling of invalid page."""
        page, _, _ = validate_pagination(page=-1)
        assert page == 1

    def test_handles_invalid_page_size(self):
        """Test handling of invalid page size."""
        _, page_size, _ = validate_pagination(page_size=-1)
        assert page_size == 20  # Default

    def test_enforces_max_page_size(self):
        """Test max page size enforcement."""
        _, page_size, _ = validate_pagination(page_size=500, max_page_size=100)
        assert page_size == 100


# ============================================================================
# SORT COLUMN VALIDATION TESTS
# ============================================================================


class TestSortColumnValidation:
    """Test sort column validation function."""

    def test_validates_allowed_column(self):
        """Test validation of allowed columns."""
        result = validate_sort_column(
            "name",
            allowed_columns={"name", "created_at"},
        )
        assert result == "name"

    def test_rejects_disallowed_column(self):
        """Test rejection of disallowed columns."""
        with pytest.raises(ValueError, match="Invalid sort column"):
            validate_sort_column(
                "password",
                allowed_columns={"name", "created_at"},
            )

    def test_uses_default_for_invalid(self):
        """Test default column for invalid input."""
        result = validate_sort_column(
            "invalid",
            allowed_columns={"name", "created_at"},
            default="name",
        )
        assert result == "name"

    def test_rejects_sql_injection_in_sort(self):
        """Test SQL injection in sort column."""
        with pytest.raises(ValueError):
            validate_sort_column(
                "name; DROP TABLE users;--",
                allowed_columns={"name"},
            )


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestInjectionPreventionIntegration:
    """Integration tests for injection prevention."""

    def test_full_validation_pipeline(self, protector):
        """Test complete validation pipeline."""
        # Safe input
        result = protector.validate_input(
            "Hello World",
            max_length=100,
            check_sql=True,
            check_nosql=True,
        )
        assert result.is_valid

        # SQL injection
        result = protector.validate_input(
            "'; DROP TABLE users;--",
            check_sql=True,
        )
        assert not result.is_valid
        assert result.injection_type == InjectionType.SQL

    def test_combined_type_and_injection_validation(self):
        """Test combined type coercion and injection prevention."""

        # This mimics what tenant_context.py should do
        def validate_tenant_id(value):
            """Validate tenant_id like in middleware."""
            return validate_integer_id(value, field_name="tenant_id", min_value=1)

        # Valid tenant ID
        assert validate_tenant_id(123) == 123
        assert validate_tenant_id("456") == 456

        # SQL injection attempts should fail
        with pytest.raises(ValueError):
            validate_tenant_id("1 OR 1=1--")

        with pytest.raises(ValueError):
            validate_tenant_id("1; DROP TABLE")

        # Type confusion should fail
        with pytest.raises((ValueError, TypeError)):
            validate_tenant_id({"$gt": 0})


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_very_long_input(self, protector):
        """Test handling of very long inputs."""
        result = protector.validate_input("a" * 10000, max_length=1000)
        assert not result.is_valid
        assert "exceeds maximum length" in result.error_message

    def test_unicode_handling(self, protector):
        """Test Unicode character handling."""
        result = protector.validate_input("Hello 世界 🌍")
        assert result.is_valid

    def test_empty_string_validation(self, protector):
        """Test empty string handling."""
        result = protector.check_sql_injection("")
        assert result.is_valid

    def test_whitespace_only_string(self):
        """Test whitespace-only string handling."""
        with pytest.raises(ValueError, match="Cannot be empty"):
            validate_string_input("   ", field_name="name")

    def test_case_insensitive_detection(self, protector):
        """Test case-insensitive pattern detection."""
        # All should be detected regardless of case
        payloads = [
            "UNION SELECT",
            "union select",
            "Union Select",
            "uNiOn SeLeCt",
        ]
        for payload in payloads:
            result = protector.check_sql_injection(payload)
            assert not result.is_valid, f"Failed to detect: {payload}"


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
