"""
Service layer for tenant custom data.

Wraps TenantCustomDataRepository with validation.
"""

import logging
from typing import Any, Optional

from src.core.services.tenant_custom_data_repository import TenantCustomDataRepository

logger = logging.getLogger(__name__)

# Allowed namespace length / key length guard
_MAX_NAMESPACE_LEN = 100
_MAX_KEY_LEN = 255


class TenantCustomDataService:
    """High-level service for tenant-scoped custom data."""

    def __init__(self, repository: TenantCustomDataRepository) -> None:
        self._repo = repository

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_namespace(namespace: str) -> None:
        if not namespace or len(namespace) > _MAX_NAMESPACE_LEN:
            raise ValueError(f"Namespace must be 1-{_MAX_NAMESPACE_LEN} characters.")

    @staticmethod
    def _validate_key(key: str) -> None:
        if not key or len(key) > _MAX_KEY_LEN:
            raise ValueError(f"Key must be 1-{_MAX_KEY_LEN} characters.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_value(self, tenant_id: int, namespace: str, key: str) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Read a single value (returns None if missing)."""
        self._validate_namespace(namespace)
        self._validate_key(key)
        return await self._repo.get(tenant_id, namespace, key)

    async def set_value(self, tenant_id: int, namespace: str, key: str, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Write (upsert) a single value."""
        self._validate_namespace(namespace)
        self._validate_key(key)
        await self._repo.set(tenant_id, namespace, key, value)

    async def delete_value(self, tenant_id: int, namespace: str, key: str) -> bool:
        """Delete a single key. Returns True if deleted."""
        self._validate_namespace(namespace)
        self._validate_key(key)
        return await self._repo.delete(tenant_id, namespace, key)

    async def get_namespace(self, tenant_id: int, namespace: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return all key-value pairs in a namespace."""
        self._validate_namespace(namespace)
        return await self._repo.list_namespace(tenant_id, namespace)

    async def delete_namespace(self, tenant_id: int, namespace: str) -> int:
        """Delete an entire namespace. Returns deleted count."""
        self._validate_namespace(namespace)
        return await self._repo.delete_namespace(tenant_id, namespace)

    async def list_namespaces(self, tenant_id: int) -> list[str]:
        """Return all namespaces for a tenant."""
        return await self._repo.list_namespaces(tenant_id)


__all__ = ["TenantCustomDataService"]
