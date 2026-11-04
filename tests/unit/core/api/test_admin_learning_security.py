import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from src.core.api.admin_learning_endpoints import (
    _enforce_tenant_access,
    _is_system_admin,
    _resolve_tenant_id,
)


@pytest.mark.unit
def test_resolve_tenant_id_raises_when_tenant_missing():
    """A user without tenant_id must NEVER fall back to tenant 1."""
    user = MagicMock()
    user.tenant_id = None

    with pytest.raises(ValueError, match="tenant_id"):
        _resolve_tenant_id(user)


@pytest.mark.unit
def test_resolve_tenant_id_returns_correct_value():
    user = MagicMock()
    user.tenant_id = 42
    assert _resolve_tenant_id(user) == 42


@pytest.mark.unit
def test_resolve_tenant_id_accepts_dict_user():
    user = {"tenant_id": 7}
    assert _resolve_tenant_id(user) == 7


@pytest.mark.unit
def test_resolve_tenant_id_raises_for_dict_without_tenant():
    with pytest.raises(ValueError, match="tenant_id"):
        _resolve_tenant_id({})


# ---------------------------------------------------------------------------
# Tenant isolation helpers (ADR-026 review fix)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_system_admin_true():
    user = MagicMock()
    user.roles = ["system_admin"]
    assert _is_system_admin(user) is True


@pytest.mark.unit
def test_is_system_admin_false():
    user = MagicMock()
    user.roles = ["admin"]
    assert _is_system_admin(user) is False


@pytest.mark.unit
def test_is_system_admin_no_roles():
    user = MagicMock()
    user.roles = []
    assert _is_system_admin(user) is False


@pytest.mark.unit
def test_enforce_tenant_access_allows_own_tenant():
    user = MagicMock()
    user.tenant_id = 42
    user.roles = ["admin"]
    # Should not raise
    _enforce_tenant_access(42, user)


@pytest.mark.unit
def test_enforce_tenant_access_blocks_other_tenant():
    user = MagicMock()
    user.tenant_id = 42
    user.roles = ["admin"]
    with pytest.raises(HTTPException) as exc_info:
        _enforce_tenant_access(99, user)
    assert exc_info.value.status_code == 403
    assert "own tenant" in exc_info.value.detail.lower()


@pytest.mark.unit
def test_enforce_tenant_access_allows_system_admin_any_tenant():
    user = MagicMock()
    user.tenant_id = 42
    user.roles = ["system_admin"]
    # Should not raise even for different tenant
    _enforce_tenant_access(99, user)
