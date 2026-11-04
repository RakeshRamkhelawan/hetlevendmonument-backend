"""Security tests for retention_cleanup allowlist validation."""

import pytest

from src.core.governance.retention_cleanup import (
    _RETENTION_ALLOWED_COLUMNS,
    _RETENTION_ALLOWED_TABLES,
    _validate_retention_identifier,
)


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_table_passes():
    assert _validate_retention_identifier("users", _RETENTION_ALLOWED_TABLES, "table") == "users"
    assert (
        _validate_retention_identifier("audit_logs", _RETENTION_ALLOWED_TABLES, "table")
        == "audit_logs"
    )
    assert (
        _validate_retention_identifier("user_consents", _RETENTION_ALLOWED_TABLES, "table")
        == "user_consents"
    )
    assert (
        _validate_retention_identifier("ai_decisions", _RETENTION_ALLOWED_TABLES, "table")
        == "ai_decisions"
    )


@pytest.mark.unit
def test_valid_column_passes():
    assert (
        _validate_retention_identifier("created_at", _RETENTION_ALLOWED_COLUMNS, "column")
        == "created_at"
    )
    assert (
        _validate_retention_identifier("updated_at", _RETENTION_ALLOWED_COLUMNS, "column")
        == "updated_at"
    )
    assert (
        _validate_retention_identifier("timestamp", _RETENTION_ALLOWED_COLUMNS, "column")
        == "timestamp"
    )
    assert (
        _validate_retention_identifier("tenant_id", _RETENTION_ALLOWED_COLUMNS, "column")
        == "tenant_id"
    )


# ---------------------------------------------------------------------------
# Unhappy paths -- unknown identifiers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unknown_table_rejected():
    with pytest.raises(ValueError, match="table"):
        _validate_retention_identifier("injected_table", _RETENTION_ALLOWED_TABLES, "table")


@pytest.mark.unit
def test_unknown_column_rejected():
    with pytest.raises(ValueError, match="column"):
        _validate_retention_identifier("password", _RETENTION_ALLOWED_COLUMNS, "column")


# ---------------------------------------------------------------------------
# Unhappy paths -- SQL injection attempts
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sql_injection_table_rejected():
    with pytest.raises(ValueError):
        _validate_retention_identifier(
            "users; DROP TABLE users; --", _RETENTION_ALLOWED_TABLES, "table"
        )


@pytest.mark.unit
def test_sql_injection_union_table_rejected():
    with pytest.raises(ValueError):
        _validate_retention_identifier(
            "users UNION SELECT * FROM secrets", _RETENTION_ALLOWED_TABLES, "table"
        )


@pytest.mark.unit
def test_sql_injection_column_rejected():
    with pytest.raises(ValueError):
        _validate_retention_identifier("created_at OR 1=1", _RETENTION_ALLOWED_COLUMNS, "column")


@pytest.mark.unit
def test_empty_string_table_rejected():
    with pytest.raises(ValueError):
        _validate_retention_identifier("", _RETENTION_ALLOWED_TABLES, "table")


@pytest.mark.unit
def test_empty_string_column_rejected():
    with pytest.raises(ValueError):
        _validate_retention_identifier("", _RETENTION_ALLOWED_COLUMNS, "column")


# ---------------------------------------------------------------------------
# Allowlist immutability
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_allowed_tables_is_frozenset():
    assert isinstance(_RETENTION_ALLOWED_TABLES, frozenset)


@pytest.mark.unit
def test_allowed_columns_is_frozenset():
    assert isinstance(_RETENTION_ALLOWED_COLUMNS, frozenset)


# ---------------------------------------------------------------------------
# Error message quality
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_error_message_contains_label_and_value():
    with pytest.raises(ValueError) as exc_info:
        _validate_retention_identifier("evil_table", _RETENTION_ALLOWED_TABLES, "table")
    msg = str(exc_info.value)
    assert "table" in msg
    assert "evil_table" in msg


@pytest.mark.unit
def test_error_message_lists_allowed_values():
    with pytest.raises(ValueError) as exc_info:
        _validate_retention_identifier("bad_col", _RETENTION_ALLOWED_COLUMNS, "date column")
    msg = str(exc_info.value)
    # The error should enumerate at least one allowed value so callers can self-diagnose.
    assert "created_at" in msg
