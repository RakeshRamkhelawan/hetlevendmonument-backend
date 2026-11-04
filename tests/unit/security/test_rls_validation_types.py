"""Runtime type-contract tests for src.core.security.rls_validation."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.core.security.rls_validation import RLSViolationError, validate_resource_tenant


@dataclass
class ResourceWithTenant:
    id: int
    tenant_id: int


@dataclass
class ResourceWithoutTenant:
    id: int


class TestValidateResourceTenantTypeContract:
    """Verify validate_resource_tenant accepts HasTenantId-like objects."""

    def test_accepts_object_with_tenant_id(self) -> None:
        resource = ResourceWithTenant(id=1, tenant_id=42)
        validate_resource_tenant(resource, expected_tenant_id=42)

    def test_rejects_tenant_mismatch(self) -> None:
        resource = ResourceWithTenant(id=1, tenant_id=42)
        with pytest.raises(RLSViolationError) as exc_info:
            validate_resource_tenant(resource, expected_tenant_id=99)
        assert exc_info.value.status_code == 404

    def test_allows_missing_tenant_id_attribute(self) -> None:
        """Runtime behavior: missing tenant_id logs and allows (system tables)."""
        resource = ResourceWithoutTenant(id=1)
        validate_resource_tenant(resource, expected_tenant_id=42)  # type: ignore[arg-type]

    def test_none_resource_raises_rls(self) -> None:
        with pytest.raises(RLSViolationError) as exc_info:
            validate_resource_tenant(None, expected_tenant_id=42)
        assert exc_info.value.status_code == 404

    def test_minimal_protocol_object(self) -> None:
        """A plain object with tenant_id attribute must be accepted."""

        class MinimalTenantResource:
            tenant_id = 42
            id = 1

        validate_resource_tenant(MinimalTenantResource(), expected_tenant_id=42)
