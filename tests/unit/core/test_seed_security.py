import pytest

from src.core.database.seed import (
    _ALLOWED_TENANT_COLS,
    _ALLOWED_USER_COLS,
    _validate_seed_columns,
)


@pytest.mark.unit
def test_valid_tenant_cols_pass():
    cols = ["name", "slug", "is_active"]
    result = _validate_seed_columns(cols, _ALLOWED_TENANT_COLS, "tenant")
    assert result == cols


@pytest.mark.unit
def test_invalid_tenant_col_raises():
    with pytest.raises(ValueError, match="tenant"):
        _validate_seed_columns(["name", "injected_col"], _ALLOWED_TENANT_COLS, "tenant")


@pytest.mark.unit
def test_sql_injection_col_rejected():
    with pytest.raises(ValueError):
        _validate_seed_columns(
            ["name", "x; DROP TABLE tenants; --"],
            _ALLOWED_TENANT_COLS,
            "tenant",
        )


@pytest.mark.unit
def test_valid_user_cols_pass():
    cols = ["tenant_id", "email", "hashed_password", "is_active"]
    result = _validate_seed_columns(cols, _ALLOWED_USER_COLS, "user")
    assert result == cols


@pytest.mark.unit
def test_invalid_user_col_raises():
    with pytest.raises(ValueError, match="user"):
        _validate_seed_columns(["email", "arbitrary_field"], _ALLOWED_USER_COLS, "user")


@pytest.mark.unit
def test_empty_list_passes():
    assert _validate_seed_columns([], _ALLOWED_TENANT_COLS, "tenant") == []


@pytest.mark.unit
def test_allowlists_are_frozensets():
    assert isinstance(_ALLOWED_TENANT_COLS, frozenset)
    assert isinstance(_ALLOWED_USER_COLS, frozenset)


@pytest.mark.unit
def test_all_allowed_tenant_cols_pass():
    cols = sorted(_ALLOWED_TENANT_COLS)
    result = _validate_seed_columns(cols, _ALLOWED_TENANT_COLS, "tenant")
    assert result == cols


@pytest.mark.unit
def test_all_allowed_user_cols_pass():
    cols = sorted(_ALLOWED_USER_COLS)
    result = _validate_seed_columns(cols, _ALLOWED_USER_COLS, "user")
    assert result == cols
