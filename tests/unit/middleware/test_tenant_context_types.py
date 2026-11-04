"""Runtime type-contract tests for src.core.middleware.tenant_context."""

from __future__ import annotations

import pytest

from src.core.middleware.tenant_context import (
    clear_tenant_context,
    get_tenant_id,
    require_tenant_id,
    set_tenant_id,
)


class TestTenantContextTypeContract:
    """Verify tenant context helpers preserve int types."""

    def test_set_get_roundtrip_returns_int(self) -> None:
        set_tenant_id(42)
        try:
            result = get_tenant_id()
            assert isinstance(result, int)
            assert result == 42
        finally:
            clear_tenant_context()

    def test_set_string_converts_to_int(self) -> None:
        set_tenant_id("42")
        try:
            result = get_tenant_id()
            assert isinstance(result, int)
            assert result == 42
        finally:
            clear_tenant_context()

    def test_require_tenant_id_returns_int(self) -> None:
        set_tenant_id(42)
        try:
            result = require_tenant_id()
            assert isinstance(result, int)
            assert result == 42
        finally:
            clear_tenant_context()

    def test_require_tenant_id_raises_when_none(self) -> None:
        clear_tenant_context()
        with pytest.raises(RuntimeError):
            require_tenant_id()

    def test_clear_tenant_context_sets_none(self) -> None:
        set_tenant_id(42)
        clear_tenant_context()
        assert get_tenant_id() is None
