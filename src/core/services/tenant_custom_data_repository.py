"""
Repository for tenant_custom_data EAV table.

Provides typed CRUD operations scoped by tenant_id + namespace + key.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.models.tenant_custom_data import TenantCustomData

logger = logging.getLogger(__name__)


class TenantCustomDataRepository:
    """Repository for the tenant_custom_data EAV table."""

    def __init__(
        self, session_or_factory: async_sessionmaker[AsyncSession] | AsyncSession
    ) -> None:
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        if isinstance(session_or_factory, async_sessionmaker):
            self._session_factory = session_or_factory
        else:
            self._session = session_or_factory

    def _get_session(self) -> AsyncSession:
        """Get session from factory or return direct session."""
        if self._session is not None:
            return self._session
        if self._session_factory is not None:
            return self._session_factory()
        raise RuntimeError("No session or session_factory available")

    async def get(self, tenant_id: int, namespace: str, key: str) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get a single value. Returns None if not found."""
        session = self._get_session()
        stmt = select(TenantCustomData.value).where(
            TenantCustomData.tenant_id == tenant_id,
            TenantCustomData.namespace == namespace,
            TenantCustomData.key == key,
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        return row

    async def set(self, tenant_id: int, namespace: str, key: str, value: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Upsert a value (INSERT ... ON CONFLICT UPDATE)."""
        data = {
            "tenant_id": tenant_id,
            "namespace": namespace,
            "key": key,
            "value": value,
            "updated_at": datetime.now(timezone.utc),
        }
        session = self._get_session()
        stmt = pg_insert(TenantCustomData).values(**data)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_tenant_custom_data",
            set_={
                "value": data["value"],
                "updated_at": data["updated_at"],
            },
        )
        await session.execute(stmt)
        await session.commit()

    async def delete(self, tenant_id: int, namespace: str, key: str) -> bool:
        """Delete a single key. Returns True if a row was deleted."""
        session = self._get_session()
        stmt = delete(TenantCustomData).where(
            TenantCustomData.tenant_id == tenant_id,
            TenantCustomData.namespace == namespace,
            TenantCustomData.key == key,
        )
        result = await session.execute(stmt)
        await session.commit()
        return getattr(result, "rowcount", 0) > 0

    async def list_namespace(self, tenant_id: int, namespace: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return all key-value pairs in a namespace."""
        session = self._get_session()
        stmt = (
            select(TenantCustomData.key, TenantCustomData.value)
            .where(
                TenantCustomData.tenant_id == tenant_id,
                TenantCustomData.namespace == namespace,
            )
            .order_by(TenantCustomData.key)
        )
        result = await session.execute(stmt)
        rows = result.all()
        return {row.key: row.value for row in rows}

    async def delete_namespace(self, tenant_id: int, namespace: str) -> int:
        """Delete all data in a namespace. Returns deleted count."""
        session = self._get_session()
        stmt = delete(TenantCustomData).where(
            TenantCustomData.tenant_id == tenant_id,
            TenantCustomData.namespace == namespace,
        )
        result = await session.execute(stmt)
        await session.commit()
        return getattr(result, "rowcount", 0)

    async def list_namespaces(self, tenant_id: int) -> list[str]:
        """Return all unique namespaces for a tenant."""
        session = self._get_session()
        stmt = (
            select(TenantCustomData.namespace)
            .where(TenantCustomData.tenant_id == tenant_id)
            .distinct()
            .order_by(TenantCustomData.namespace)
        )
        result = await session.execute(stmt)
        return [row[0] for row in result.all()]


__all__ = ["TenantCustomDataRepository"]
