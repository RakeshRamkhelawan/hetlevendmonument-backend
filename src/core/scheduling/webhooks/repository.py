"""
Repository for WebhookRegistration and SyncConflict models.

Provides CRUD operations with tenant isolation.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.webhooks.models import SyncConflict, WebhookRegistration


class WebhookRepository:
    """Repository for webhook registration operations with tenant isolation."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self._tenant_id = tenant_id

    # ========================================================================
    # Webhook Registration CRUD
    # ========================================================================

    async def get_by_id(self, registration_id: str) -> WebhookRegistration | None:
        """Get webhook registration by ID, ensuring it belongs to the tenant."""
        result = await self.db.execute(
            select(WebhookRegistration).where(
                and_(
                    WebhookRegistration.id == registration_id,
                    WebhookRegistration.tenant_id == self._tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_channel_id(self, channel_id: str) -> WebhookRegistration | None:
        """Get webhook registration by Google channel ID, with tenant isolation."""
        result = await self.db.execute(
            select(WebhookRegistration).where(
                and_(
                    WebhookRegistration.channel_id == channel_id,
                    WebhookRegistration.tenant_id == self._tenant_id,
                    WebhookRegistration.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_subscription_id(self, subscription_id: str) -> WebhookRegistration | None:
        """Get webhook registration by Outlook subscription ID, with tenant isolation."""
        result = await self.db.execute(
            select(WebhookRegistration).where(
                and_(
                    WebhookRegistration.subscription_id == subscription_id,
                    WebhookRegistration.tenant_id == self._tenant_id,
                    WebhookRegistration.is_active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_integration(self, integration_id: str) -> list[WebhookRegistration]:
        """List all webhook registrations for an integration."""
        result = await self.db.execute(
            select(WebhookRegistration)
            .where(WebhookRegistration.integration_id == integration_id)
            .order_by(WebhookRegistration.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_expiring(self, hours: int = 24) -> list[WebhookRegistration]:
        """List webhook registrations expiring within specified hours."""
        threshold = datetime.now(timezone.utc) + timedelta(hours=hours)

        result = await self.db.execute(
            select(WebhookRegistration).where(
                and_(
                    WebhookRegistration.is_active.is_(True),
                    WebhookRegistration.expiration_date <= threshold,
                )
            )
        )
        return list(result.scalars().all())

    async def create(
        self,
        integration_id: str,
        provider: str,
        expiration_date: datetime,
        channel_id: str | None = None,
        resource_id: str | None = None,
        subscription_id: str | None = None,
        client_state: str | None = None,
    ) -> WebhookRegistration:
        """Create a new webhook registration with tenant isolation."""
        registration = WebhookRegistration(
            tenant_id=self._tenant_id,
            integration_id=integration_id,
            provider=provider,
            channel_id=channel_id,
            resource_id=resource_id,
            subscription_id=subscription_id,
            client_state=client_state,
            expiration_date=expiration_date,
            is_active=True,
        )
        self.db.add(registration)
        await self.db.flush()
        return registration

    async def deactivate(self, registration_id: str) -> bool:
        """Deactivate a webhook registration (soft delete)."""
        registration = await self.get_by_id(registration_id)
        if not registration:
            return False

        registration.is_active = False
        await self.db.flush()
        return True

    async def delete(self, registration_id: str) -> bool:
        """Hard delete a webhook registration."""
        registration = await self.get_by_id(registration_id)
        if not registration:
            return False

        await self.db.delete(registration)
        await self.db.flush()
        return True


class SyncConflictRepository:
    """Repository for sync conflict operations with tenant isolation."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self._tenant_id = tenant_id

    # ========================================================================
    # Sync Conflict CRUD
    # ========================================================================

    async def get_by_id(self, conflict_id: str) -> SyncConflict | None:
        """Get sync conflict by ID, ensuring it belongs to the tenant."""
        result = await self.db.execute(
            select(SyncConflict).where(
                and_(
                    SyncConflict.id == conflict_id,
                    SyncConflict.tenant_id == self._tenant_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_integration(
        self,
        integration_id: str,
        status: str | None = None,
    ) -> list[SyncConflict]:
        """List sync conflicts for an integration."""
        query = select(SyncConflict).where(SyncConflict.integration_id == integration_id)

        if status:
            query = query.where(SyncConflict.resolution_status == status)

        query = query.order_by(SyncConflict.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_pending(self, integration_id: str | None = None) -> list[SyncConflict]:
        """List pending (unresolved) sync conflicts."""
        query = select(SyncConflict).where(SyncConflict.resolution_status == "pending")

        if integration_id:
            query = query.where(SyncConflict.integration_id == integration_id)

        query = query.order_by(SyncConflict.severity.desc(), SyncConflict.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        integration_id: str,
        local_event_id: str,
        external_event_id: str,
        conflict_type: str,
        severity: str,
        local_snapshot: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        external_snapshot: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> SyncConflict:
        """Create a new sync conflict record with tenant isolation."""
        conflict = SyncConflict(
            tenant_id=self._tenant_id,
            integration_id=integration_id,
            local_event_id=local_event_id,
            external_event_id=external_event_id,
            conflict_type=conflict_type,
            severity=severity,
            local_snapshot=local_snapshot,
            external_snapshot=external_snapshot,
            resolution_status="pending",
        )
        self.db.add(conflict)
        await self.db.flush()
        return conflict

    async def mark_resolved(
        self,
        conflict_id: str,
        strategy: str,
        resolved_by: str,
    ) -> bool:
        """Mark a conflict as manually resolved."""
        conflict = await self.get_by_id(conflict_id)
        if not conflict:
            return False

        conflict.mark_resolved(strategy, resolved_by)
        await self.db.flush()
        return True

    async def mark_auto_resolved(
        self,
        conflict_id: str,
        strategy: str,
    ) -> bool:
        """Mark a conflict as auto-resolved by system."""
        conflict = await self.get_by_id(conflict_id)
        if not conflict:
            return False

        conflict.mark_auto_resolved(strategy)
        await self.db.flush()
        return True

    async def delete(self, conflict_id: str) -> bool:
        """Hard delete a conflict record."""
        conflict = await self.get_by_id(conflict_id)
        if not conflict:
            return False

        await self.db.delete(conflict)
        await self.db.flush()
        return True
