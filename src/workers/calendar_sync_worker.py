"""
Background worker for calendar synchronization.

Follows same pattern as workflow_worker.py with:
- Dramatiq + Redis broker
- Async PostgreSQL sessions
- Proper error handling and retries

Usage:
    # Start worker
    dramatiq src.workers.calendar_sync_worker -p 2 -t 4

    # Enqueue task programmatically
    from src.workers.calendar_sync_worker import sync_calendar_integration
    sync_calendar_integration.send(integration_id="abc-123")
"""

import asyncio
import logging
from typing import Any

# Import existing infrastructure from workflow_worker
from src.workers.workflow_worker import (
    _DRAMATIQ_AVAILABLE,
    MAX_RETRIES,
    get_async_session_maker,
)

logger = logging.getLogger(__name__)

# NOTE: pyright ignores needed -- dramatiq @actor redeclares these module-level names.
sync_calendar_integration: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
refresh_expiring_webhooks: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]

# Initialize Dramatiq if available
# NOTE: de actors hieronder binden via `workflow_actor` aan de echte RedisBroker (ADR-036 OP-13).
# Actors registered here are automatically copied to RedisBroker at runtime.
if _DRAMATIQ_AVAILABLE:
    from src.core.tasks.dramatiq_broker import workflow_actor

    @workflow_actor(
        queue_name="calendar_sync",
        max_retries=MAX_RETRIES,
        time_limit=300000,  # 5 minutes
    )
    async def sync_calendar_integration(integration_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Background task to sync a calendar integration.

        Args:
            integration_id: The calendar integration ID to sync

        Returns:
            Dict with sync results

        Raises:
            Exception: If sync fails (will be retried)
        """
        from src.core.scheduling.integrations.google_calendar import GoogleCalendarProvider
        from src.core.scheduling.integrations.outlook_calendar import OutlookCalendarProvider
        from src.core.scheduling.integrations.repository import CalendarIntegrationRepository
        from src.core.scheduling.integrations.sync_service import CalendarSyncService

        logger.info(f"Starting calendar sync for integration {integration_id}")

        async with get_async_session_maker()() as session:
            try:
                # Initialize providers
                providers = {
                    "google": GoogleCalendarProvider(),
                    "outlook": OutlookCalendarProvider(),
                }

                # Get integration
                repo = CalendarIntegrationRepository(session)
                integration = await repo.get_by_id_any(integration_id)

                if not integration:
                    logger.warning(f"Integration not found: {integration_id}")
                    return {"status": "error", "reason": "integration_not_found"}

                if not integration.is_active:
                    logger.info(f"Integration {integration_id} is inactive, skipping sync")
                    return {"status": "skipped", "reason": "integration_inactive"}

                # Perform sync
                sync_service = CalendarSyncService(
                    db=session,
                    providers=providers,
                    integration_repo=repo,
                )

                result = await sync_service.sync_integration(integration)

                # Update last_synced_at
                from datetime import datetime, timezone

                integration.last_synced_at = datetime.now(timezone.utc)
                await session.commit()

                logger.info(
                    f"Calendar sync completed for {integration_id}: "
                    f"created={result.created}, updated={result.updated}, "
                    f"deleted={result.deleted}, errors={len(result.errors)}"
                )

                return {
                    "status": "success",
                    "integration_id": integration_id,
                    "created": result.created,
                    "updated": result.updated,
                    "deleted": result.deleted,
                    "errors": len(result.errors),
                    "sync_token": result.next_sync_token,
                }

            except Exception as exc:
                logger.exception(f"Calendar sync failed for {integration_id}")
                await session.rollback()
                raise

    @workflow_actor(
        queue_name="calendar_sync",
        max_retries=MAX_RETRIES,
        time_limit=300000,  # 5 minutes
    )
    async def refresh_expiring_webhooks() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Periodic task to refresh webhooks expiring within 24 hours.

        This task should be scheduled to run every 12 hours via Dramatiq's
        scheduling system or an external cron job.
        """
        from src.core.scheduling.webhooks.registration_service import WebhookRegistrationService

        logger.info("Starting webhook refresh task")

        async with get_async_session_maker()() as session:
            service = WebhookRegistrationService(session, tenant_id=1)

            try:
                result = await service.refresh_expiring_webhooks(hours_before=24)

                logger.info(
                    f"Webhook refresh completed: refreshed={result['refreshed']}, "
                    f"failed={result['failed']}, total={result['total']}"
                )

                return {
                    "status": "success",
                    "refreshed": result["refreshed"],
                    "failed": result["failed"],
                    "total": result["total"],
                }

            except Exception as exc:
                logger.exception("Webhook refresh task failed")
                await session.rollback()
                raise

else:
    # Testing mode: provide dummy tasks that can be mocked
    class _DummySender:
        """Dummy object with .send() method for test patching."""

        def send(self, *args: Any, **kwargs: Any) -> Any:
            logger.debug(f"Dummy task send called with args={args}, kwargs={kwargs}")
            return None

    sync_calendar_integration = _DummySender()  # pyright: ignore[reportAssignmentType]
    refresh_expiring_webhooks = _DummySender()  # pyright: ignore[reportAssignmentType]


# ============================================================================
# CLI for Testing
# ============================================================================

if __name__ == "__main__":
    """
    Test worker locally.

    Usage:
        python -m src.workers.calendar_sync_worker
    """
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    async def test() -> None:
        if len(sys.argv) > 1:
            integration_id = sys.argv[1]
            logger.info(f"Testing sync for integration: {integration_id}")

            if _DRAMATIQ_AVAILABLE:
                result = await sync_calendar_integration(integration_id)  # pyright: ignore[reportGeneralTypeIssues]
                logger.info(f"Result: {result}")
            else:
                logger.warning("Dramatiq not available (testing mode)")
        else:
            logger.info("Usage: python -m src.workers.calendar_sync_worker <integration_id>")

    asyncio.run(test())
