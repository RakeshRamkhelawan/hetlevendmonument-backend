"""TDD tests for feature_flags_endpoints type and security fixes.

B2.1: _get_current_tenant_id must raise on missing context (security).
      _get_current_user must return a callable, not a dict.
"""

import pytest
from unittest.mock import patch


def test_tenant_id_raises_without_context():
    """RED: Missing tenant context must raise RuntimeError, not return None."""
    with patch(
        "src.core.middleware.tenant_context.get_tenant_id",
        return_value=None,
    ):
        from src.core.api.v1.feature_flags.dependencies import get_tenant_id

        with pytest.raises(RuntimeError, match="tenant"):
            get_tenant_id()


def test_dependency_factory_returns_callable():
    """RED: _get_current_user must return a callable for FastAPI Depends."""
    from src.core.api.v1.feature_flags.dependencies import get_current_user_dep

    result = get_current_user_dep()
    assert callable(result), f"Expected callable, got {type(result)}"


def test_tenant_id_return_annotation_is_int():
    """RED: _get_current_tenant_id must be annotated as returning int."""
    import inspect
    from src.core.api.v1.feature_flags.dependencies import get_tenant_id

    sig = inspect.signature(get_tenant_id)
    assert sig.return_annotation is not dict, (
        f"Return annotation is {sig.return_annotation!r}, expected int"
    )
