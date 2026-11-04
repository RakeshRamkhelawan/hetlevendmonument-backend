"""
Dramatiq worker for async feedback processing.

Provides background task processing for:
- Feedback analysis and insight generation
- Batch processing of queued feedback
- Adaptation rule generation from insights
"""

import os
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any, TypedDict

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AsyncIO, CurrentMessage
from loguru import logger
from sqlalchemy import delete
from sqlalchemy.sql.dml import Delete

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_DATABASE_URL: str | None = None
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_database_url() -> str:
    global _DATABASE_URL
    if _DATABASE_URL is None:
        _DATABASE_URL = os.environ.get("DATABASE_URL")
        if not _DATABASE_URL:
            raise RuntimeError("DATABASE_URL environment variable is required")
    return _DATABASE_URL


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            _get_database_url(),
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _async_session_maker


from src.core.noodstop import model_deur  # noqa: F401  (opstartpunt: meldt de noodstopcontrole van de modeldeur aan)
from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.metrics import (
    record_twin_retention_deleted,
    set_twin_hard_delete_pending,
)
from src.core.learning.service import FeedbackProcessingService
from src.core.learning.twin_models import TwinSuggestionLog, UserBehaviorObservation
from src.core.utils.best_effort import best_effort


class FeedbackPayload(TypedDict, total=False):
    """Feedback data passed via Dramatiq message bus (JSON-serialized, tenant_id is str)."""

    conversation_id: str
    tenant_id: str
    rating: int
    comment: str | None
    corrected_supervisor: str | None
    confidence: float
    context: dict[str, object]


class InsightCleanupDict(TypedDict):
    """Return type for cleanup_old_insights actor."""

    tenant_id: str
    days: int
    archived: int
    deleted: int


class ObservationCleanupDict(TypedDict):
    """Return type for cleanup_expired_observations actor (NOT _run_observation_cleanup)."""

    status: str
    observations: int


class CostLogCleanupDict(TypedDict):
    """Return type for twin_cost_log_retention_cleanup actor (NOT _run_cost_log_cleanup)."""

    status: str
    suggestion_logs: int


# Configure this module's own broker.
#
# Uses REDIS_URL env var; falls back to internal Docker service name so that the
# worker never accidentally connects to a host-mapped port like localhost:6380.
#
# BEWUST GEEN dramatiq.set_broker() (2026-08-01): die aanroep verving de PROCESBREDE
# broker zodra deze module werd geimporteerd. Omdat @dramatiq.actor bij decoratie bindt
# aan get_broker(), bepaalde de IMPORTVOLGORDE op welke broker actors terechtkwamen --
# in productie net zo goed als in tests. src/workers/actors.py documenteerde dat zelfs als
# load-bearing regel ("this must come BEFORE the actor side-effect imports below"). Het
# importeren van deze module maakte daardoor 4 tests in andere bestanden rood, en in
# productie kan het betekenen dat achtergrondtaken op de verkeerde broker landen en dus
# nooit worden uitgevoerd.
#
# In plaats daarvan bindt elke actor hieronder EXPLICIET aan _broker, en benoemt de
# entrypoint de broker bij naam: `dramatiq src.core.learning.worker:_broker`
# (docker-compose*.yml). Zo is er geen globale staat meer in het spel en is de
# importvolgorde irrelevant. Afgedwongen door
# tests/architecture/test_dramatiq_broker_isolation.py.
_redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0").strip()
_broker = RedisBroker(
    url=_redis_url
)  # keep default middleware (Retries, TimeLimit, etc.)  # type: ignore[no-untyped-call]  # Dramatiq/Prometheus lacks stubs
_broker.add_middleware(
    AsyncIO()
)  # add async support for async def actors  # type: ignore[no-untyped-call]  # Dramatiq/Prometheus lacks stubs


@dramatiq.actor(broker=_broker, max_retries=3, time_limit=30000)
async def process_feedback_async(
    feedback_data: dict[
        str, Any  # TODO(TYPE): replace Any with concrete type
    ],  # Dramatiq deserializes JSON to plain dict; see FeedbackPayload  # TODO(TYPE): replace Any with concrete type
) -> dict[
    str, Any
]:  # TODO(TYPE): result needs FeedbackProcessingResult TypedDict  # TODO(TYPE): replace Any with concrete type
    """
    Process feedback asynchronously in background.

    This actor is called when feedback is submitted via the API.
    It handles the heavy lifting of insight generation and rule creation.

    Args:
        feedback_data: {
            "conversation_id": str,
            "tenant_id": str,
            "rating": int,
            "comment": str,
            "corrected_supervisor": str,
            "confidence": float,
            "context": dict
        }

    Returns:
        Processing result with insight_id and rule_id
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "process_feedback_started",
        worker_message_id=message_id,
        tenant_id=feedback_data.get("tenant_id"),
    )

    from src.core.middleware.tenant_context import set_tenant_id, clear_tenant_context

    tenant_id = feedback_data.get("tenant_id")
    if tenant_id:
        set_tenant_id(tenant_id)

    try:
        async with _get_session_maker()() as session:
            try:
                service = FeedbackProcessingService(session)
                result = await service.process_feedback(feedback_data)

                logger.info(
                    "process_feedback_success",
                    worker_message_id=message_id,
                    insight_id=result.get("insight_id"),
                )
                return result

            except Exception as e:
                logger.error(
                    "process_feedback_failed",
                    worker_message_id=message_id,
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )
                raise
    finally:
        if tenant_id:
            clear_tenant_context()


async def _run_hard_delete(
    user_id: str, tenant_id: int
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Core logic for hard-deleting twin data (testable without Dramatiq).

    Args:
        user_id: De user ID (van JWT, niet gehashed)
        tenant_id: De tenant ID

    Returns:
        Dict met verwijderde tabellen en status.
    """
    from src.core.database.redis import get_redis_client

    redis_client = await get_redis_client()
    async with _get_session_maker()() as session:
        consent_mgr = TwinConsentManager(db=session, cache=redis_client)
        result = await consent_mgr.hard_delete(user_id=user_id, tenant_id=tenant_id)
        return {"user_id": user_id, "tenant_id": tenant_id, "deleted": result}


@dramatiq.actor(broker=_broker, max_retries=3, time_limit=60000)
async def twin_hard_delete_async(
    user_id: str, tenant_id: int
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Hard-delete alle twin data voor een user (GDPR Artikel 17).

    Dit is een async worker die de daadwerkelijke verwijdering uitvoert
    nadat de API een 202 Accepted heeft teruggegeven.

    Args:
        user_id: De user ID (van JWT, niet gehashed)
        tenant_id: De tenant ID

    Returns:
        Dict met verwijderde tabellen en status.
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "twin_hard_delete_started",
        worker_message_id=message_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    # Import before the try so clear_tenant_context is always bound in the finally.
    from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id

    try:
        set_tenant_id(tenant_id)
        try:
            result = await _run_hard_delete(user_id=user_id, tenant_id=tenant_id)
            logger.info(
                "twin_hard_delete_success",
                worker_message_id=message_id,
                user_id=user_id,
                deleted_tables=list(result.get("deleted", {}).keys()),
            )
        except Exception as e:
            logger.error(
                "twin_hard_delete_failed",
                worker_message_id=message_id,
                user_id=user_id,
                error_type=type(e).__name__,
                error=str(e),
                exc_info=True,
            )
            raise
    finally:
        clear_tenant_context()

    # Update pending count gauge in best-effort block so a metric failure
    # never fails the already-successful actor.
    async with best_effort("twin_hard_delete_pending_gauge"):
        pending = await _count_pending_hard_deletes()
        set_twin_hard_delete_pending(pending)

    return result


async def _count_pending_hard_deletes() -> int:
    """Count users with pending hard delete requests (for metrics)."""
    from sqlalchemy import func, select

    from src.core.learning.twin_models import UserTwinConsent

    async with _get_session_maker()() as session:
        result = await session.execute(
            select(func.count())
            .select_from(UserTwinConsent)
            .where(UserTwinConsent.hard_delete_requested.is_(True))
        )
        return result.scalar() or 0


@dramatiq.actor(broker=_broker, max_retries=2, time_limit=60000)
async def batch_process_feedback(
    feedback_list: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Process multiple feedback items in batch.

    Useful for nightly processing of accumulated feedback.

    Args:
        feedback_list: List[Any] of feedback data dicts  # TODO(TYPE): replace Any with concrete type

    Returns: List[Any] of processing results  # TODO(TYPE): replace Any with concrete type
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "batch_process_feedback_started",
        worker_message_id=message_id,
        item_count=len(feedback_list),
    )

    results: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
    from src.core.middleware.tenant_context import set_tenant_id, clear_tenant_context

    async with _get_session_maker()() as session:
        service = FeedbackProcessingService(session)

        for i, feedback_data in enumerate(feedback_list):
            tenant_id = feedback_data.get("tenant_id")
            if tenant_id:
                set_tenant_id(tenant_id)
            try:
                result = await service.process_feedback(feedback_data)
                results.append(result)
                logger.debug(
                    "batch_process_feedback_item_complete",
                    worker_message_id=message_id,
                    item_index=i + 1,
                    total=len(feedback_list),
                )
            except Exception as e:
                logger.error(
                    "batch_process_feedback_item_failed",
                    worker_message_id=message_id,
                    item_index=i,
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True,
                )
                results.append(
                    {
                        "processed": False,
                        "error": str(e),
                        "conversation_id": feedback_data.get("conversation_id"),
                    }
                )
            finally:
                if tenant_id:
                    clear_tenant_context()

    successful = sum(1 for r in results if r.get("processed"))
    logger.info(
        "batch_process_feedback_complete",
        worker_message_id=message_id,
        successful=successful,
        total=len(feedback_list),
    )

    return results


@dramatiq.actor(broker=_broker, max_retries=1, time_limit=30000)
async def generate_adaptation_rule_from_insight(
    insight_id: str, tenant_id: str
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Generate adaptation rule from existing insight.

    This can be called when an insight is marked as actionable
    but no rule was created initially.

    Args:
        insight_id: ID of the learning insight
        tenant_id: Tenant identifier

    Returns:
        Result with rule_id if created
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "generate_adaptation_rule_started",
        worker_message_id=message_id,
        insight_id=insight_id,
        tenant_id=tenant_id,
    )

    from src.core.middleware.tenant_context import set_tenant_id, clear_tenant_context

    if tenant_id:
        set_tenant_id(tenant_id)
    try:
        async with _get_session_maker()() as session:
            # Rule generation from existing insight is not yet implemented.
            # When implemented, this would fetch the insight, analyze it, and create a rule.
            logger.warning(
                "generate_adaptation_rule_not_implemented",
                worker_message_id=message_id,
                insight_id=insight_id,
            )
            return {"insight_id": insight_id, "rule_created": False}
    finally:
        if tenant_id:
            clear_tenant_context()


@dramatiq.actor(broker=_broker, max_retries=2, time_limit=120000)
async def cleanup_old_insights(tenant_id: str, days: int = 90) -> InsightCleanupDict:
    """
    Clean up old processed insights to save database space.

    Args:
        tenant_id: Tenant to clean up
        days: Age in days before cleanup

    Returns:
        Cleanup statistics
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "cleanup_old_insights_started",
        worker_message_id=message_id,
        tenant_id=tenant_id,
        days=days,
    )

    # Cleanup logic not yet implemented.
    # When implemented, this would archive old insights and remove processed ones.
    logger.warning(
        "cleanup_old_insights_not_implemented",
        worker_message_id=message_id,
        tenant_id=tenant_id,
    )
    return {"tenant_id": tenant_id, "days": days, "archived": 0, "deleted": 0}


async def _verwijder_per_tenant(
    session: AsyncSession, bouw_statement: Callable[[], Delete], wat: str
) -> int:
    """Verwijdert PER TENANT, met de tenantcontext per ronde aangenomen (ADR-036 OP-155).

    **Waarom niet in een keer.** Deze opruimtaken draaiden als EEN globale `DELETE ... WHERE
    expires_at < now`, zonder tenantcontext. `user_behavior_observations` en
    `twin_suggestion_log` hebben allebei een `tenant_id` EN een RLS-policy. Na de
    omschakeling naar `sanskritisetu_app` bepaalt `USING` bij een DELETE eerst WELKE RIJEN
    zichtbaar zijn; zonder tenantcontext zijn dat er nul.

    Gemeten 2026-09-16 op dezelfde policyvorm:

        DELETE zonder tenantcontext  ->  DELETE 0, GEEN fout, commit slaagt

    Deze taken zouden dan `deleted=0` loggen, `record_twin_retention_deleted(..., 0)`
    vastleggen, en als geslaagd gelden -- een AVG-bewaartermijn die groen meldt terwijl er
    niets wordt opgeruimd. Voor `user_behavior_observations` gold dat AL voor deze wijziging:
    die tabel had zijn policy al.

    Dit is het patroon dat de vakliteratuur voor batchverwerking aanbeveelt: een lus per
    tenant met de context per ronde, in plaats van een verbinding die alles mag zien. De
    tenant-ids komen uit de database, nooit uit invoer.

    Gevonden door de Gate 2-securityreview van 2026-09-15.
    """
    from typing import Any, cast

    from sqlalchemy import select
    from sqlalchemy.engine import CursorResult

    from src.core.database.bypass_session import adopt_tenant
    from src.core.models.rbac_models import Tenant

    tenant_ids = [r[0] for r in (await session.execute(select(Tenant.id))).all()]
    totaal = 0
    for tenant_id in tenant_ids:
        async with adopt_tenant(session, tenant_id):
            # `AsyncSession.execute` is getypeerd als `Result`, dat geen `rowcount` kent.
            # Een DELETE levert in werkelijkheid altijd een `CursorResult`; zonder deze
            # cast is het een pyright-fout (de baseline is 0).
            resultaat = cast("CursorResult[Any]", await session.execute(bouw_statement()))
            totaal += resultaat.rowcount or 0
    await session.commit()
    logger.info("%s: verwijderd=%s over %s tenants", wat, totaal, len(tenant_ids))
    return totaal


async def _run_observation_cleanup() -> dict[str, int]:
    """
    Core logic for cleaning up expired behavior observations (testable without Dramatiq).

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(timezone.utc)

    async with _get_session_maker()() as session:
        # Per tenant, met de context per ronde -- zie `_verwijder_per_tenant`.
        deleted = await _verwijder_per_tenant(
            session,
            lambda: delete(UserBehaviorObservation).where(
                UserBehaviorObservation.expires_at.is_not(None),
                UserBehaviorObservation.expires_at < now,
            ),
            "twin_observation_cleanup",
        )

    logger.info("twin_observation_cleanup_complete: deleted=%s", deleted)
    record_twin_retention_deleted("user_behavior_observations", deleted)
    return {"observations": deleted}


async def _run_cost_log_cleanup() -> dict[str, int]:
    """
    Core logic for cleaning up expired twin suggestion logs (testable without Dramatiq).

    Returns:
        Dict with count of deleted records.
    """
    now = datetime.now(timezone.utc)

    async with _get_session_maker()() as session:
        # Per tenant, met de context per ronde -- zie `_verwijder_per_tenant`.
        deleted = await _verwijder_per_tenant(
            session,
            lambda: delete(TwinSuggestionLog).where(
                TwinSuggestionLog.expires_at < now,
            ),
            "twin_cost_log_cleanup",
        )

    logger.info("twin_cost_log_cleanup_complete: deleted=%s", deleted)
    record_twin_retention_deleted("twin_suggestion_log", deleted)
    return {"suggestion_logs": deleted}


@dramatiq.actor(broker=_broker, max_retries=2, time_limit=120000)
async def cleanup_expired_observations() -> ObservationCleanupDict:
    """
    Daily cleanup of expired twin behavior observations.

    - user_behavior_observations: 90-day retention (AVG Art. 5(1)(e))

    Scheduled daily at 03:00 UTC via APScheduler in scheduler.py.
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "cleanup_expired_observations_started",
        worker_message_id=message_id,
    )

    try:
        result = await _run_observation_cleanup()
        logger.info(
            "cleanup_expired_observations_complete",
            worker_message_id=message_id,
            observations_deleted=result["observations"],
        )
        return ObservationCleanupDict(status="completed", observations=result["observations"])
    except Exception as e:
        logger.error(
            "cleanup_expired_observations_failed",
            worker_message_id=message_id,
            error_type=type(e).__name__,
            error=str(e),
            exc_info=True,
        )
        raise


@dramatiq.actor(broker=_broker, max_retries=2, time_limit=120000)
async def twin_cost_log_retention_cleanup() -> CostLogCleanupDict:
    """
    Daily cleanup of expired twin suggestion logs (cost tracking).

    - twin_suggestion_log: 7-year retention (Dutch tax law art. 52 AWR)

    Scheduled daily at 03:15 UTC via APScheduler in scheduler.py.
    Independent actor: a failure here never blocks observation cleanup.
    """
    current_message = CurrentMessage.get_current_message()
    message_id = (
        current_message.message_id  # pyright: ignore[reportAttributeAccessIssue]
        if current_message
        else "unknown"  # TODO(TYPE): replace Any with concrete type
    )
    logger.info(
        "twin_cost_log_retention_cleanup_started",
        worker_message_id=message_id,
    )

    try:
        result = await _run_cost_log_cleanup()
        logger.info(
            "twin_cost_log_retention_cleanup_complete",
            worker_message_id=message_id,
            suggestion_logs_deleted=result["suggestion_logs"],
        )
        return CostLogCleanupDict(status="completed", suggestion_logs=result["suggestion_logs"])
    except Exception as e:
        logger.error(
            "twin_cost_log_retention_cleanup_failed",
            worker_message_id=message_id,
            error_type=type(e).__name__,
            error=str(e),
            exc_info=True,
        )
        raise


# Convenience functions for enqueueing tasks
def enqueue_feedback_processing(
    feedback_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
) -> "dramatiq.Message[Any]":
    """
    Enqueue feedback for async processing.

    Usage:
        from src.core.learning.worker import enqueue_feedback_processing
        enqueue_feedback_processing({
            "conversation_id": "conv_123",
            "tenant_id": "tenant_abc",
            "rating": 1,
            ...
        })
    """
    return process_feedback_async.send(feedback_data)


def enqueue_batch_processing(
    feedback_list: list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
) -> "dramatiq.Message[Any]":
    """Enqueue batch processing of feedback."""
    return batch_process_feedback.send(feedback_list)


def enqueue_expired_observation_cleanup() -> "dramatiq.Message[Any]":
    """Enqueue daily cleanup of expired observations."""
    return cleanup_expired_observations.send()


def enqueue_twin_cost_log_cleanup() -> "dramatiq.Message[Any]":
    """Enqueue daily cleanup of expired twin cost logs."""
    return twin_cost_log_retention_cleanup.send()


# Scheduled task configuration (for dramatiq-periodic).
# NOTE: Twin cleanup actors (cleanup_expired_observations, twin_cost_log_retention_cleanup)
# are scheduled via APScheduler in scheduler.py to avoid duplicate scheduling.
# Only add non-twin actors here.
SCHEDULED_TASKS = [
    {
        "cron": "0 2 * * *",  # Daily at 2 AM
        "actor": batch_process_feedback,
        "args": ([],),  # Empty list - will be populated by query
        "options": {"queue": "learning"},
    },
    {
        "cron": "0 3 * * 0",  # Weekly on Sunday at 3 AM
        "actor": cleanup_old_insights,
        "args": ("all", 90),
        "options": {"queue": "maintenance"},
    },
]
