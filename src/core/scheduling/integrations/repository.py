"""
Repository for CalendarIntegration with mandatory tenant isolation.

Handles encrypted token storage via TokenEncryptionService.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.integrations.models import CalendarIntegration
from src.core.scheduling.integrations.token_encryption import TokenEncryptionService


class CalendarIntegrationRepository:
    """CRUD for CalendarIntegration rows.

    Tokens are encrypted on write and decrypted on read so that callers
    never touch ciphertext directly.
    """

    def __init__(
        self,
        db: AsyncSession,
        encryption: TokenEncryptionService | None = None,
    ) -> None:
        self.db = db
        self._enc = encryption or TokenEncryptionService()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, integration_id: str, tenant_id: int) -> CalendarIntegration | None:
        result = await self.db.execute(
            select(CalendarIntegration).where(
                and_(
                    CalendarIntegration.id == integration_id,
                    CalendarIntegration.tenant_id == tenant_id,
                    CalendarIntegration.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_any(self, integration_id: str) -> CalendarIntegration | None:
        """Get integration by ID without tenant filtering (for internal use).

        SECURITY: Only use this method when tenant context is not available
        (e.g., webhook processing, background jobs).
        """
        result = await self.db.execute(
            select(CalendarIntegration).where(
                and_(
                    CalendarIntegration.id == integration_id,
                    CalendarIntegration.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_user_provider(
        self, tenant_id: int, user_id: str, provider: str
    ) -> CalendarIntegration | None:
        result = await self.db.execute(
            select(CalendarIntegration).where(
                and_(
                    CalendarIntegration.tenant_id == tenant_id,
                    CalendarIntegration.user_id == user_id,
                    CalendarIntegration.provider == provider,
                    CalendarIntegration.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_any_by_user_provider(
        self, tenant_id: int, user_id: str, provider: str
    ) -> CalendarIntegration | None:
        result = await self.db.execute(
            select(CalendarIntegration).where(
                and_(
                    CalendarIntegration.tenant_id == tenant_id,
                    CalendarIntegration.user_id == user_id,
                    CalendarIntegration.provider == provider,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, tenant_id: int, user_id: str) -> list[CalendarIntegration]:
        result = await self.db.execute(
            select(CalendarIntegration)
            .where(
                and_(
                    CalendarIntegration.tenant_id == tenant_id,
                    CalendarIntegration.user_id == user_id,
                    CalendarIntegration.is_deleted.is_(False),
                )
            )
            .order_by(CalendarIntegration.provider)
        )
        return list(result.scalars().all())

    async def list_active_by_provider(
        self, tenant_id: int, provider: str
    ) -> list[CalendarIntegration]:
        result = await self.db.execute(
            select(CalendarIntegration).where(
                and_(
                    CalendarIntegration.tenant_id == tenant_id,
                    CalendarIntegration.provider == provider,
                    CalendarIntegration.is_active.is_(True),
                    CalendarIntegration.is_deleted.is_(False),
                )
            )
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        tenant_id: int,
        user_id: str,
        provider: str,
        provider_account_id: str,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
        token_scope: str | None = None,
        provider_calendar_id: str = "primary",
    ) -> CalendarIntegration:
        integration = CalendarIntegration(
            tenant_id=tenant_id,
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_calendar_id=provider_calendar_id,
            access_token_encrypted=self._enc.encrypt(access_token),
            refresh_token_encrypted=(self._enc.encrypt(refresh_token) if refresh_token else None),
            token_expires_at=token_expires_at,
            token_scope=token_scope,
        )
        self.db.add(integration)
        await self.db.flush()
        return integration

    async def update_tokens(
        self,
        integration: CalendarIntegration,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> CalendarIntegration:
        integration.access_token_encrypted = self._enc.encrypt(access_token)
        if refresh_token is not None:
            integration.refresh_token_encrypted = self._enc.encrypt(refresh_token)
        if token_expires_at is not None:
            integration.token_expires_at = token_expires_at
        await self.db.flush()
        return integration

    async def restore_and_update(
        self,
        integration: CalendarIntegration,
        *,
        provider_account_id: str,
        access_token: str,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
        token_scope: str | None = None,
        provider_calendar_id: str = "primary",
    ) -> CalendarIntegration:
        integration.restore()
        integration.is_active = True
        integration.provider_account_id = provider_account_id
        integration.provider_calendar_id = provider_calendar_id
        integration.token_scope = token_scope
        integration.access_token_encrypted = self._enc.encrypt(access_token)
        integration.refresh_token_encrypted = (
            self._enc.encrypt(refresh_token) if refresh_token else None
        )
        integration.token_expires_at = token_expires_at
        integration.sync_token = None
        integration.last_synced_at = None
        await self.db.flush()
        return integration

    async def update_sync_state(
        self,
        integration: CalendarIntegration,
        sync_token: str | None,
        synced_at: datetime | None = None,
    ) -> CalendarIntegration:
        integration.sync_token = sync_token
        integration.last_synced_at = synced_at or datetime.now(timezone.utc)
        await self.db.flush()
        return integration

    async def deactivate(self, integration_id: str, tenant_id: int) -> bool:
        integration = await self.get_by_id(integration_id, tenant_id)
        if not integration:
            return False
        integration.is_active = False
        await self.db.flush()
        return True

    async def soft_delete(self, integration_id: str, tenant_id: int) -> bool:
        integration = await self.get_by_id(integration_id, tenant_id)
        if not integration:
            return False
        integration.is_active = False
        integration.soft_delete()
        await self.db.flush()
        return True

    # ------------------------------------------------------------------
    # Helpers -- decrypt tokens for service use
    # ------------------------------------------------------------------

    def decrypt_access_token(self, integration: CalendarIntegration) -> str:
        """Decrypt the stored access token.

        Args:
            integration: CalendarIntegration with encrypted token

        Returns:
            Plaintext access token
        """
        return self._enc.decrypt(integration.access_token_encrypted)

    def decrypt_refresh_token(self, integration: CalendarIntegration) -> str | None:
        """Decrypt the stored refresh token if present.

        Args:
            integration: CalendarIntegration with optional encrypted refresh token

        Returns:
            Plaintext refresh token, or None if not stored
        """
        if not integration.refresh_token_encrypted:
            return None
        return self._enc.decrypt(integration.refresh_token_encrypted)
