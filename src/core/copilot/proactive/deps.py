"""
Concrete dependencies for ProactiveScheduler startup wiring (WE-020/021).

Provides:
- _DBTenantRepo: TenantRepo Protocol backed by the tenants/users DB tables
- _ProactiveServiceProxy: fresh CopilotService per submit_proactive_proposal call
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class _DBTenantRepo:
    """TenantRepo Protocol implementation using the async session factory.

    Creates a fresh DB session per method call (scheduler is long-lived).
    """

    def __init__(self, session_factory: Callable[..., Any]) -> None:
        self._session_factory = session_factory

    async def list_active_ids(self) -> list[int]:
        """Return IDs of all active tenants."""
        from src.core.models.rbac_models import Tenant

        async with self._session_factory() as db:
            result = await db.execute(select(Tenant.id).where(Tenant.is_active.is_(True)))
            return list(result.scalars().all())

    async def get_primary_admin_user_id(self, tenant_id: int) -> int:
        """Return the primary admin (is_superuser) user_id for a tenant."""
        from src.core.models.rbac_models import User

        async with self._session_factory() as db:
            result = await db.execute(
                select(User.id)
                .where(User.tenant_id == tenant_id)
                .where(User.is_active.is_(True))
                .where(User.is_superuser.is_(True))
                .limit(1)
            )
            user_id = result.scalar_one_or_none()
            if user_id is None:
                # Fallback: first active user for this tenant
                result2 = await db.execute(
                    select(User.id)
                    .where(User.tenant_id == tenant_id)
                    .where(User.is_active.is_(True))
                    .limit(1)
                )
                user_id = result2.scalar_one_or_none() or 0
            return int(user_id)

    async def get_platform_admin_tenant_id(self) -> int:
        """Return the first active tenant_id (platform-wide signals)."""
        ids = await self.list_active_ids()
        return ids[0] if ids else 1

    async def get_tenant_id_for_user(self, user_id: int) -> int | None:
        """Return the tenant_id that owns the given user."""
        from src.core.models.rbac_models import User

        async with self._session_factory() as db:
            result = await db.execute(select(User.tenant_id).where(User.id == user_id).limit(1))
            return cast(int | None, result.scalar_one_or_none())

    async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None:
        """Return the tenant_id that owns the given workflow (stub -- post-MVP)."""
        # TODO(post-MVP): implement real workflow tenant lookup
        logger.debug(
            "get_tenant_id_for_workflow: stub returns None for workflow_id=%s",
            workflow_id,
        )
        return None


class _ProactiveServiceProxy:
    """Creates a fresh CopilotService per submit_proactive_proposal call.

    Avoids long-lived DB sessions in the ProactiveScheduler.
    """

    def __init__(self, session_factory: Callable[..., Any]) -> None:
        self._session_factory = session_factory

    async def submit_proactive_proposal(
        # TODO(TYPE): replace Any with concrete type
        self,
        proposal: Any,
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Build a fresh CopilotService and delegate the proposal."""
        from src.core.copilot.dependencies import _build_copilot_service

        async with self._session_factory() as db:
            service = await _build_copilot_service(db)
            return await service.submit_proactive_proposal(proposal)
