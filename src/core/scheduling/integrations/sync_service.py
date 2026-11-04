"""
Two-way calendar synchronisation service.

Pulls external events from Google / Outlook into local CalendarEvent rows,
and pushes local changes to external calendars.  Uses incremental sync
tokens when available.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.config import scheduling_config
from src.core.scheduling.integrations.base_provider import (
    BaseCalendarProvider,
    ExternalEvent,
    SyncResult,
)
from src.core.scheduling.integrations.models import CalendarIntegration
from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.repository import CalendarEventRepository

logger = logging.getLogger(__name__)


class CalendarSyncService:
    """Orchestrates bidirectional sync between local and external calendars."""

    def __init__(
        self,
        db: AsyncSession,
        providers: dict[str, BaseCalendarProvider],
        integration_repo: CalendarIntegrationRepository | None = None,
        event_repo: CalendarEventRepository | None = None,
    ) -> None:
        self.db = db
        self._providers = providers
        self._integ_repo = integration_repo or CalendarIntegrationRepository(db)
        self._event_repo = event_repo or CalendarEventRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def sync_integration(
        self,
        integration: CalendarIntegration,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
    ) -> SyncResult:
        """Pull external events and upsert local CalendarEvent rows.

        Returns a SyncResult with created / updated / deleted counters.
        """
        provider = self._get_provider(integration.provider)

        # Ensure a valid access token
        access_token = await self._ensure_valid_token(integration, provider)

        now = datetime.now(tz=timezone.utc)
        if time_min is None:
            time_min = now - timedelta(days=7)
        if time_max is None:
            time_max = now + timedelta(days=scheduling_config.DEFAULT_SYNC_WINDOW_DAYS)

        external_events, next_sync_token = await provider.list_events(
            access_token=access_token,
            time_min=time_min,
            time_max=time_max,
            sync_token=integration.sync_token,
            calendar_id=integration.provider_calendar_id,
        )

        result = SyncResult()

        # Use bulk operations for better performance
        if len(external_events) > 10:
            # Bulk sync for large datasets
            result = await self._bulk_sync_events(
                integration=integration,
                external_events=external_events,
                next_sync_token=next_sync_token,
            )
        else:
            # Individual processing for small datasets (better error handling)
            for ext_evt in external_events:
                try:
                    await self._upsert_local_event(
                        integration=integration,
                        ext_evt=ext_evt,
                        result=result,
                    )
                except Exception as exc:
                    msg = f"Failed to upsert event {ext_evt.external_id}: {exc}"
                    logger.warning(msg)
                    result.errors.append(msg)

            # Persist sync state
            result.next_sync_token = next_sync_token
            await self._integ_repo.update_sync_state(integration, sync_token=next_sync_token)

        logger.info(
            "Sync completed for integration %s: +%d ~%d -%d (errors: %d)",
            integration.id,
            result.created,
            result.updated,
            result.deleted,
            len(result.errors),
        )
        return result

    async def push_event(
        self,
        integration: CalendarIntegration,
        local_event: CalendarEvent,
    ) -> str | None:
        """Push a local CalendarEvent to the external calendar.

        Returns the external event id (or None on failure).
        """
        provider = self._get_provider(integration.provider)
        access_token = await self._ensure_valid_token(integration, provider)

        ext = ExternalEvent(
            external_id="",
            title=local_event.title,
            start_time=local_event.start_time,
            end_time=local_event.end_time,
            description=local_event.description,
            location=local_event.location,
        )

        try:
            external_id = await provider.create_event(
                access_token=access_token,
                event=ext,
                calendar_id=integration.provider_calendar_id,
            )
            return external_id
        except Exception:
            logger.exception(
                "Failed to push event %s to %s",
                local_event.id,
                integration.provider,
            )
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_provider(self, provider_name: str) -> BaseCalendarProvider:
        """Get a calendar provider by name.

        Args:
            provider_name: Name of the provider (e.g., "google", "outlook")

        Returns:
            The requested BaseCalendarProvider instance

        Raises:
            ValueError: If the provider is not registered
        """
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider

    async def _ensure_valid_token(
        self,
        integration: CalendarIntegration,
        provider: BaseCalendarProvider,
    ) -> str:
        """Return a valid access token, refreshing if needed.

        Args:
            integration: CalendarIntegration with stored tokens
            provider: BaseCalendarProvider for token refresh

        Returns:
            Valid access token string ready for API calls

        Note:
            Handles timezone-naive datetime from SQLite by treating as UTC.
        """
        expires_at = integration.token_expires_at
        if expires_at and expires_at.tzinfo is None:
            # SQLite may return naive datetimes; treat them as UTC.
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at and expires_at > datetime.now(tz=timezone.utc) + timedelta(minutes=5):
            return self._integ_repo.decrypt_access_token(integration)

        refresh_token = self._integ_repo.decrypt_refresh_token(integration)
        if not refresh_token:
            return self._integ_repo.decrypt_access_token(integration)

        tokens = await provider.refresh_access_token(refresh_token)
        await self._integ_repo.update_tokens(
            integration,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            token_expires_at=tokens.expires_at,
        )
        return tokens.access_token

    async def _bulk_sync_events(
        self,
        integration: CalendarIntegration,
        external_events: list[ExternalEvent],
        next_sync_token: str | None,
    ) -> SyncResult:
        """Sync multiple events using bulk operations for better performance.

        Args:
            integration: CalendarIntegration for the sync
            external_events: List of ExternalEvent objects to sync
            next_sync_token: Token for incremental syncs on next call

        Returns:
            SyncResult with created/updated/deleted counters and error list
        """
        from sqlalchemy import select

        result = SyncResult()

        # Get all existing external IDs for this integration
        existing_result = await self.db.execute(
            select(CalendarEvent).where(
                and_(
                    CalendarEvent.tenant_id == integration.tenant_id,
                    CalendarEvent.is_deleted.is_(False),
                    CalendarEvent.metadata_json["provider"].as_string() == integration.provider,
                )
            )
        )
        existing_events = {
            e.metadata_json.get("external_id"): e
            for e in existing_result.scalars().all()
            if e.metadata_json and e.metadata_json.get("external_id")
        }

        events_to_create: list[CalendarEvent] = []
        events_to_update: list[CalendarEvent] = []

        for ext_evt in external_events:
            try:
                if self._is_deleted_external_event(ext_evt):
                    existing = existing_events.get(ext_evt.external_id)
                    if existing:
                        existing.soft_delete()
                        existing.status = "cancelled"
                        meta = existing.metadata_json or {}
                        meta["external_deleted_at"] = datetime.now(tz=timezone.utc).isoformat()
                        existing.metadata_json = meta
                        result.deleted += 1
                    continue

                existing = existing_events.get(ext_evt.external_id)
                if existing:
                    # Update existing
                    existing.title = ext_evt.title
                    existing.description = ext_evt.description
                    existing.start_time = ext_evt.start_time
                    existing.end_time = ext_evt.end_time
                    existing.location = ext_evt.location
                    meta = existing.metadata_json or {}
                    meta["external_updated_at"] = datetime.now(tz=timezone.utc).isoformat()
                    existing.metadata_json = meta
                    events_to_update.append(existing)
                    result.updated += 1
                else:
                    # Create new
                    event = CalendarEvent(
                        tenant_id=integration.tenant_id,
                        title=ext_evt.title,
                        description=ext_evt.description,
                        start_time=ext_evt.start_time,
                        end_time=ext_evt.end_time,
                        location=ext_evt.location,
                        organizer_id=integration.user_id,
                        event_type="external",
                        status=(
                            "confirmed"
                            if ext_evt.status in ("confirmed", "busy", "tentative")
                            else ext_evt.status
                        ),
                        metadata_json={
                            "external_id": ext_evt.external_id,
                            "provider": integration.provider,
                            "provider_calendar_id": integration.provider_calendar_id,
                            "synced_at": datetime.now(tz=timezone.utc).isoformat(),
                        },
                    )
                    events_to_create.append(event)
                    result.created += 1

            except Exception as exc:
                msg = f"Failed to process event {ext_evt.external_id}: {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        # Bulk operations
        if events_to_create:
            for event in events_to_create:
                self.db.add(event)
        if events_to_update:
            # Already tracked by SQLAlchemy, just flush
            pass

        await self.db.flush()

        # Persist sync state
        result.next_sync_token = next_sync_token
        await self._integ_repo.update_sync_state(integration, sync_token=next_sync_token)

        return result

    async def _upsert_local_event(
        self,
        integration: CalendarIntegration,
        ext_evt: ExternalEvent,
        result: SyncResult,
    ) -> None:
        """Create or update a local CalendarEvent from an external event.

        Args:
            integration: CalendarIntegration owning the event
            ext_evt: External event to sync
            result: SyncResult to accumulate counters and errors

        Side effects:
            Modifies result counters (created/updated/deleted)
        """
        # Check if we already track this external event via metadata
        existing = await self._find_by_external_id(
            tenant_id=integration.tenant_id,
            external_id=ext_evt.external_id,
            provider=integration.provider,
        )

        if self._is_deleted_external_event(ext_evt):
            if existing:
                existing.soft_delete()
                existing.status = "cancelled"
                meta = existing.metadata_json or {}
                meta["external_deleted_at"] = datetime.now(tz=timezone.utc).isoformat()
                existing.metadata_json = meta
                await self.db.flush()
                result.deleted += 1
            return

        if existing:
            existing.title = ext_evt.title
            existing.description = ext_evt.description
            existing.start_time = ext_evt.start_time
            existing.end_time = ext_evt.end_time
            existing.location = ext_evt.location
            meta = existing.metadata_json or {}
            meta["external_updated_at"] = datetime.now(tz=timezone.utc).isoformat()
            existing.metadata_json = meta
            await self.db.flush()
            result.updated += 1
        else:
            event = CalendarEvent(
                tenant_id=integration.tenant_id,
                title=ext_evt.title,
                description=ext_evt.description,
                start_time=ext_evt.start_time,
                end_time=ext_evt.end_time,
                location=ext_evt.location,
                organizer_id=integration.user_id,
                event_type="external",
                status=(
                    "confirmed"
                    if ext_evt.status in ("confirmed", "busy", "tentative")
                    else ext_evt.status
                ),
                metadata_json={
                    "external_id": ext_evt.external_id,
                    "provider": integration.provider,
                    "provider_calendar_id": (integration.provider_calendar_id),
                    "synced_at": (datetime.now(tz=timezone.utc).isoformat()),
                },
            )
            self.db.add(event)
            await self.db.flush()
            result.created += 1

    async def _find_by_external_id(
        self,
        tenant_id: int,
        external_id: str,
        provider: str,
    ) -> CalendarEvent | None:
        """Find a local CalendarEvent by its external_id metadata.

        Args:
            tenant_id: Tenant isolation filter
            external_id: External provider's event ID
            provider: Provider name (e.g., "google")

        Returns:
            CalendarEvent if found, None otherwise

        Note:
            Uses JSON query on metadata_json["external_id"].
            Works on both PostgreSQL and SQLite (JSON1 extension).
        """
        # JSON query: metadata_json->>'external_id' = ...
        # Works on both PostgreSQL and SQLite (via JSON1 extension).
        from sqlalchemy import and_, select

        result = await self.db.execute(
            select(CalendarEvent).where(
                and_(
                    CalendarEvent.tenant_id == tenant_id,
                    CalendarEvent.is_deleted.is_(False),
                    CalendarEvent.metadata_json["external_id"].as_string() == external_id,
                    CalendarEvent.metadata_json["provider"].as_string() == provider,
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _is_deleted_external_event(ext_evt: ExternalEvent) -> bool:
        """Check if an external event is marked as deleted.

        Args:
            ext_evt: ExternalEvent to check

        Returns:
            True if event status is cancelled/deleted or raw metadata indicates deletion
        """
        status = (ext_evt.status or "").lower()
        raw = ext_evt.raw or {}
        return status in {"cancelled", "deleted"} or bool(raw.get("deleted") or raw.get("@removed"))
