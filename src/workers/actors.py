"""
Dramatiq Actors for Background Jobs

This module contains all Dramatiq actors for background task processing.
Actors are organized by queue name for better resource management.

Queues:
- default: General purpose tasks
- maintenance: Scheduled maintenance tasks (pack health, cleanup, etc.)
- calendar_sync: Calendar synchronization tasks
- workflow: Workflow execution tasks (in workflow_worker.py)

Usage:
    # Enqueue a task
    from src.workers.actors import run_pack_health_aggregation
    run_pack_health_aggregation.send()
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    import dramatiq as _dramatiq_typing

    from src.core.jobs.retention_cleanup_job import RetentionJobResult

# Import existing infrastructure from workflow_worker. De volgorde van de imports hieronder doet er niet meer
# toe: elke actor bindt EXPLICIET aan `workflow_broker` (src/core/tasks/dramatiq_broker.py), er is geen
# procesbrede broker meer die door een eerdere import gezet moet zijn (ADR-036 OP-13).
from src.workers.workflow_worker import _DRAMATIQ_AVAILABLE, MAX_RETRIES

# Re-export GDPR purge actor so the workflow worker discovers it.
from src.core.actors.gdpr_purge import purge_user_data  # noqa: F401

# NOTE: imports below are purely for side-effect Dramatiq actor registration.
# F401 (imported but unused) is expected -- noqa: F401 per import.
# Calendar actors: WEL laden. De eerdere uitsluiting droeg als reden dat
# calendar_sync_worker via src/workers/__init__.py workflow_worker importeert en dat die
# DATABASE_URL bij import vereist. Die reden is op 2026-08-17 weerlegd door meting: dit
# bestand zit in datzelfde pakket, dus die importketen liep sowieso al. Met de
# omgevingsvariabelen van de container geladen laden alle drie de modules samen zonder
# fout en registreren beide actors zich op de broker (22 stuks).
# Zonder deze import consumeerde geen enkel proces de queue `calendar_sync`:
# handlers.py:203 schreef in het niets en webhooks die binnen 24 uur verliepen werden
# nooit vernieuwd. Geborgd door tests/architecture/test_every_dispatched_actor_is_loaded_by_a_worker.py.
from src.workers.calendar_sync_worker import (  # noqa: F401
    refresh_expiring_webhooks,
    sync_calendar_integration,
)
from src.core.copilot.api.contest_service import notify_tenant_admins_of_contest  # noqa: F401
from src.core.copilot.audit.integrity_check_actor import (
    check_hash_chain_integrity_actor,
)  # noqa: F401
from src.core.copilot.audit.report_jobs import generate_audit_report  # noqa: F401
from src.core.governance.retention_cleanup import cleanup_council_decisions  # noqa: F401
from src.domains.memory.tasks import purge_soft_deleted_memory_items  # noqa: F401
from src.core.tasks.audit_tasks import write_audit_log_task  # noqa: F401
from src.core.tasks.debiteuren_tasks import verstuur_klare_berichten  # noqa: F401
from src.core.tasks.debiteuren_tasks import volg_debiteuren_op  # noqa: F401
from src.core.tasks.hr_termijn_tasks import signaleer_hr_termijnen  # noqa: F401
from src.core.tasks.bonnen_opruimen import ruim_bonnen_op  # noqa: F401
from src.core.tasks.cva_tasks import process_cva_message  # noqa: F401
from src.core.tasks.workflow_tasks import execute_workflow_step  # noqa: F401

logger = logging.getLogger(__name__)

try:
    from src.core.observability.metrics import (
        STALE_CLEANUP_ERRORS_TOTAL,
        STALE_CLEANUP_RUNS_TOTAL,
        STALE_CLEANUP_TASKS_FAILED_TOTAL,
    )
except Exception:
    # Fallback for test environments where metrics registry isn't set up
    STALE_CLEANUP_RUNS_TOTAL = None  # type: ignore[assignment]
    STALE_CLEANUP_TASKS_FAILED_TOTAL = None  # type: ignore[assignment]
    STALE_CLEANUP_ERRORS_TOTAL = None  # type: ignore[assignment]

# Initialize Dramatiq if available
# NOTE: elke actor hieronder bindt via `workflow_actor` aan de echte RedisBroker; er is geen stub.
# NOTE: pyright ignores needed -- dramatiq @actor redeclares these module-level names.
run_pack_health_aggregation: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
run_daily_maintenance: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
run_ml_model_training: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
run_retention_cleanup: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
run_twin_profile_aggregation: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
run_audit_verification: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
cleanup_stale_tasks: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
cleanup_expired_hitl_tickets: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
process_document_async: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]
export_foundation_archives: Any = None  # pyright: ignore[reportRedeclaration, reportAssignmentType]


async def _run_stale_task_cleanup() -> dict[str, int]:
    """
    Mark stuck PENDING/RUNNING/RETRYING tasks as FAILED (ADR-007: 1-hour timeout).

    Stale criteria:
    - PENDING + created_at < NOW() - 1h + started_at IS NULL
    - RUNNING + started_at < NOW() - 1h
    - RETRYING + started_at < NOW() - 1h (retry loop stuck)

    Uses TenantFilterBypass so the worker process (no request middleware) can
    query across all tenants. The ORM hook would otherwise inject WHERE 1=0.
    """
    from datetime import timedelta

    from sqlalchemy import and_, or_, select

    from src.core.database.session import get_db_session
    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.workflow.models import C7ExecutionTask, TaskStatus

    if STALE_CLEANUP_RUNS_TOTAL is not None:
        STALE_CLEANUP_RUNS_TOTAL.inc()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    now = datetime.now(timezone.utc)
    count = 0

    try:
        async with get_db_session() as session:
            with TenantFilterBypass():
                result = await session.execute(
                    select(C7ExecutionTask).where(
                        or_(
                            and_(
                                C7ExecutionTask.status == TaskStatus.PENDING,
                                C7ExecutionTask.created_at < cutoff,
                                C7ExecutionTask.started_at.is_(None),
                            ),
                            and_(
                                C7ExecutionTask.status == TaskStatus.RUNNING,
                                C7ExecutionTask.started_at < cutoff,
                            ),
                            and_(
                                C7ExecutionTask.status == TaskStatus.RETRYING,
                                C7ExecutionTask.started_at < cutoff,
                            ),
                        )
                    )
                )
            stale = result.scalars().all()

            for task in stale:
                task.status = TaskStatus.FAILED
                task.finished_at = now
                task.error_json = {
                    "type": "StaleTaskError",
                    "message": "Stale task cleanup: exceeded 1-hour timeout",
                }
                count += 1

            await session.commit()

        if STALE_CLEANUP_TASKS_FAILED_TOTAL is not None:
            STALE_CLEANUP_TASKS_FAILED_TOTAL.inc(count)
        return {"stale_tasks_marked_failed": count}
    except Exception:
        if STALE_CLEANUP_ERRORS_TOTAL is not None:
            STALE_CLEANUP_ERRORS_TOTAL.inc()
        raise


if _DRAMATIQ_AVAILABLE:
    from src.core.tasks.dramatiq_broker import workflow_actor

    @workflow_actor(
        queue_name="maintenance",
        max_retries=MAX_RETRIES,
        time_limit=600000,  # 10 minutes
    )
    async def run_pack_health_aggregation() -> (
        dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ):  # TODO(TYPE): replace Any with concrete type
        """
        Background task to aggregate pack usage and calculate health status.

        This task should be scheduled to run daily (e.g., at 02:00 AM)
        via Dramatiq's scheduling system or an external cron job.

        Returns:
            Dict with aggregation results

        Raises:
            Exception: If aggregation fails (will be retried)
        """
        from src.core.database.tenant_query_filter import TenantFilterBypass
        from src.core.jobs.pack_health_job import update_pack_metrics

        logger.info("Starting pack health aggregation job")

        try:
            with TenantFilterBypass():
                await update_pack_metrics()

            logger.info("Pack health aggregation completed successfully")
            return {
                "status": "success",
                "message": "Pack health metrics updated",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.exception("Pack health aggregation failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=3,
        time_limit=300000,  # 5 minutes
    )
    async def run_daily_maintenance() -> (
        dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ):  # TODO(TYPE): replace Any with concrete type
        """
        Daily maintenance task that runs all maintenance jobs.

        This is a convenience actor that runs all daily maintenance tasks
        in sequence. Individual tasks can also be triggered separately.

        Returns:
            Dict with maintenance results
        """
        from datetime import datetime

        logger.info("Starting daily maintenance tasks")

        results = {
            "pack_health": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Run pack health aggregation
        try:
            from src.core.database.tenant_query_filter import TenantFilterBypass
            from src.core.jobs.pack_health_job import update_pack_metrics

            with TenantFilterBypass():
                await update_pack_metrics()
            results["pack_health"] = "success"
            logger.info("Pack health aggregation completed")
        except Exception as e:
            results["pack_health"] = "failed: %s" % e
            logger.error("Pack health aggregation failed: %s", e)

        logger.info("Daily maintenance tasks completed")
        return {
            "status": "completed",
            "results": results,
        }

    @workflow_actor(
        queue_name="ml",
        max_retries=MAX_RETRIES,
        time_limit=1800000,  # 30 minutes - ML training can take time
    )
    async def run_ml_model_training() -> (
        dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ):  # TODO(TYPE): replace Any with concrete type
        """
        Background task to train the ML pack recommendation model.

        This task should be scheduled to run daily (e.g., at 03:00 AM)
        via Dramatiq's scheduling system or an external cron job.

        Returns:
            Dict with training results and metrics

        Raises:
            Exception: If training fails (will be retried)
        """
        from src.core.jobs.ml_training_job import train_pack_recommendation_model

        logger.info("Starting ML model training job")

        try:
            result = await train_pack_recommendation_model()

            if result.get("status") == "success":
                logger.info("ML model training completed successfully")
            elif result.get("status") == "skipped":
                logger.warning("ML model training skipped: %s", result.get("reason"))
            else:
                logger.error("ML model training failed: %s", result.get("error"))

            return result

        except Exception as e:
            logger.exception("ML model training failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=MAX_RETRIES,
        time_limit=900000,  # 15 minutes - retention cleanup can take time
    )
    async def run_retention_cleanup() -> "RetentionJobResult":
        """
        Background task to enforce data retention policies.

        This task cleans up expired data according to jurisdiction-specific
        retention policies (GDPR, CCPA, etc.). Should be scheduled daily.

        Returns:
            Dict with cleanup statistics

        Raises:
            Exception: If cleanup fails (will be retried)
        """
        from src.core.jobs.retention_cleanup_job import run_retention_cleanup as cleanup

        logger.info("Starting retention cleanup job")

        try:
            result = await cleanup()

            if result.get("completed"):
                logger.info(
                    "Retention cleanup completed: %d records deleted",
                    result.get("total_records_deleted", 0),
                )
            else:
                logger.error("Retention cleanup did not complete successfully")

            return result

        except Exception as e:
            logger.exception("Retention cleanup failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=MAX_RETRIES,
        time_limit=300000,  # 5 minutes
    )
    async def run_prana_refill() -> dict[str, int]:
        """Daily idempotent reset of every tenant/department prana budget (ADR-021)."""
        from src.core.jobs.prana_refill_job import run_prana_refill as _refill

        logger.info("Starting prana refill job")
        try:
            return await _refill()
        except Exception as e:
            logger.exception("Prana refill failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=MAX_RETRIES,
        time_limit=300000,  # 5 minutes
    )
    async def run_avg_purge_vervallen() -> dict[str, int]:
        """Dagelijks: plan de purge in voor gebruikers van wie de AVG-termijn van 30 dagen om is."""
        from src.core.jobs.avg_purge_job import run_avg_purge_vervallen as _planner

        logger.info("Starting AVG purge planner")
        try:
            return await _planner()
        except Exception as e:
            logger.exception("AVG purge planner failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=3,
        time_limit=300000,  # 5 minutes
    )
    async def run_twin_profile_aggregation() -> (
        dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ):  # TODO(TYPE): replace Any with concrete type
        """Aggregate Digital Twin observations into cognitive profiles.

        Processes all users with unaggregated observations and updates
        their UserCognitiveProfile entries.
        """
        from src.core.jobs.twin_profile_aggregation_job import (
            aggregate_all_profiles,
        )

        logger.info("Starting twin profile aggregation job")

        try:
            result = await aggregate_all_profiles()
            logger.info(
                "Twin profile aggregation completed: %d profiles updated",
                result.get("processed", 0),
            )
            return result

        except Exception as e:
            logger.exception("Twin profile aggregation failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=MAX_RETRIES,
        time_limit=600000,  # 10 minutes
    )
    async def run_audit_verification() -> (
        dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ):  # TODO(TYPE): replace Any with concrete type
        """Verify audit trail hash chain integrity for all active tenants.

        Scheduled daily at 03:00 AM. Uses TenantFilterBypass for cross-tenant
        tenant enumeration, then verifies hash chain per tenant.
        """
        from src.core.database.session import get_db_session
        from src.core.database.tenant_query_filter import TenantFilterBypass
        from src.core.jobs.audit_verification import AuditTrailVerificationJob

        logger.info("Starting audit trail verification job")

        try:
            async with get_db_session() as session:
                with TenantFilterBypass():
                    job = AuditTrailVerificationJob(db_session=session)
                    result = await job.run()

            logger.info(
                "Audit trail verification completed: %d verified, %d failed, %d broken chains",
                result.verified_tenants,
                result.failed_tenants,
                result.total_broken_chains,
            )
            return {
                "status": "success" if result.failed_tenants == 0 else "partial_failure",
                "total_tenants": result.total_tenants,
                "verified_tenants": result.verified_tenants,
                "failed_tenants": result.failed_tenants,
                "total_entries_checked": result.total_entries_checked,
                "total_broken_chains": result.total_broken_chains,
                "duration_ms": result.duration_ms,
            }

        except Exception as e:
            logger.exception("Audit trail verification failed: %s", e)
            raise

    @workflow_actor(
        queue_name="maintenance",
        max_retries=MAX_RETRIES,
        time_limit=120000,  # 2 minutes
    )
    async def cleanup_stale_tasks() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Mark stuck PENDING/RUNNING tasks as FAILED (ADR-007: 1-hour timeout).

        Scheduled hourly. Uses TenantFilterBypass so this worker process
        (no request middleware, no tenant ContextVar) can query all tenants.
        """
        try:
            result = await _run_stale_task_cleanup()
            logger.info(
                "stale_task_cleanup_complete: %d tasks marked FAILED",
                result["stale_tasks_marked_failed"],
            )
            return result
        except Exception as e:
            logger.exception("stale_task_cleanup_failed: %s", e)
            raise

    @workflow_actor(
        queue_name="cleanup",
        max_retries=MAX_RETRIES,
        time_limit=60000,  # 1 minute
    )
    async def cleanup_expired_hitl_tickets() -> (
        dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ):  # TODO(TYPE): replace Any with concrete type
        """Mark past-SLA pending HITL tickets as expired (ADR-005, B-018 fix).

        Scheduled hourly at :15. Uses TenantFilterBypass so this worker process
        (no request middleware, no tenant ContextVar) can query across all tenants.
        The ORM hook would otherwise inject WHERE 1=0 and silently skip all tenants.

        Cleanup guarantee: at most one hourly run late for tickets that expire
        between the tenant-discovery query and the per-tenant update loop.
        """
        try:
            from sqlalchemy import select

            from src.core.database.session import get_db_session
            from src.core.database.tenant_query_filter import TenantFilterBypass
            from src.core.tool_broker.hitl_repository import HITLTicketRepository
            from src.core.tool_broker.models import HITLTicket

            now = datetime.now(timezone.utc)
            count = 0

            async with get_db_session() as session:
                with TenantFilterBypass():
                    # Discover which tenants have expired tickets (cross-tenant query).
                    tid_result = await session.execute(
                        select(HITLTicket.tenant_id)
                        .where(
                            HITLTicket.status == "pending",
                            HITLTicket.expires_at < now,
                        )
                        .distinct()
                    )
                    tenant_ids = list(tid_result.scalars().all())

                    repo = HITLTicketRepository(session)
                    for tid in tenant_ids:
                        count += await repo.cleanup_expired(tid)

                await session.commit()

            logger.info("hitl_cleanup.expired_tickets_marked: %d", count)
            return {"expired_tickets_marked": count}
        except Exception as e:
            logger.exception("hitl_cleanup_failed: %s", e)
            raise

    @workflow_actor(
        queue_name="default",
        max_retries=3,
        time_limit=300000,  # 5 minutes
    )
    async def process_document_async(
        document_id: str, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process a document asynchronously.

        Updates document status from 'processing' to 'ready' or 'error'.
        Creates a DocumentVersion snapshot on success.
        """
        from sqlalchemy import select

        from src.core.database.session import get_db_session
        from src.core.database.tenant_query_filter import TenantFilterBypass
        from src.domains.documents.models import Document, DocumentVersion

        logger.info("document_processing.start: doc_id=%s tenant=%s", document_id, tenant_id)

        try:
            async with get_db_session() as session:
                with TenantFilterBypass():
                    result = await session.execute(
                        select(Document).where(
                            Document.id == int(document_id),
                            Document.tenant_id == tenant_id,
                        )
                    )
                    doc = result.scalar_one_or_none()

                    if not doc:
                        logger.warning("document_processing.not_found: doc_id=%s", document_id)
                        return {"status": "error", "reason": "document_not_found"}

                    # Simulate processing (in production: OCR, text extraction, etc.)
                    doc.status = "ready"
                    doc.updated_at = datetime.now(timezone.utc)

                    # Create version snapshot
                    snapshot = {
                        "filename": doc.filename,
                        "mime_type": doc.mime_type,
                        "file_size_bytes": doc.file_size_bytes,
                        "storage_path": doc.storage_path,
                        "checksum_sha256": doc.checksum_sha256,
                        "metadata": doc.metadata_,
                        "content": doc.content,
                    }
                    version = DocumentVersion(
                        document_id=doc.id,
                        tenant_id=doc.tenant_id,
                        version=doc.version,
                        snapshot=snapshot,
                    )
                    session.add(version)
                    await session.commit()

            logger.info("document_processing.complete: doc_id=%s status=ready", document_id)
            return {"status": "success", "document_id": document_id, "new_status": "ready"}

        except Exception as e:
            logger.exception("document_processing.failed: doc_id=%s error=%s", document_id, e)
            # Update status to error
            try:
                async with get_db_session() as session:
                    with TenantFilterBypass():
                        result = await session.execute(
                            select(Document).where(
                                Document.id == int(document_id),
                                Document.tenant_id == tenant_id,
                            )
                        )
                        doc = result.scalar_one_or_none()
                        if doc:
                            doc.status = "error"
                            doc.updated_at = datetime.now(timezone.utc)
                            await session.commit()
            except Exception:
                logger.exception("document_processing.error_update_failed: doc_id=%s", document_id)
            raise


class ArchiveRunResult(TypedDict):
    exported: int
    failed: int


async def _foundation_portaal_tenants() -> list[tuple[int, str, str]]:
    """Actieve tenants met portaalinstellingen: (id, slug, naam). Alleen LEZEN, over tenants heen.

    TenantFilterBypass alleen hier: de planner heeft geen tenantcontext en moet weten voor wie
    er geexporteerd wordt. Er wordt in deze functie niets geschreven.
    """
    from sqlalchemy import select

    from src.core.database.session import get_db_session
    from src.core.database.tenant_query_filter import TenantFilterBypass
    from src.core.models.foundation_content import FoundationPortalSettings
    from src.core.models.rbac_models import Tenant

    async with get_db_session() as session:
        with TenantFilterBypass():
            rijen = (
                await session.execute(
                    select(Tenant.id, Tenant.slug, Tenant.name)
                    .join(FoundationPortalSettings, FoundationPortalSettings.tenant_id == Tenant.id)
                    .where(Tenant.is_active.is_(True))
                    .order_by(Tenant.id)
                )
            ).all()
    return [(int(tid), str(slug), str(naam)) for tid, slug, naam in rijen]


async def _exporteer_archief_voor_tenant(
    tenant_id: int, slug: str, naam: str, moment: datetime
) -> None:
    """Een archiefexport voor EEN tenant, met de tenantcontext gezet voor de sessie opent.

    `database.py` zet `app.current_tenant` aan het begin van elke transactie uit de ContextVar
    (ADR-036 OP-151), dus RLS en de ORM-hook gelden voor alles wat hier leest en schrijft.
    """
    from src.core.database.session import get_db_session
    from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
    from src.core.services.foundation_archive_service import (
        TRIGGER_SCHEMA,
        ExportTenant,
        FoundationArchiveService,
    )

    from sqlalchemy.exc import SQLAlchemyError

    dienst = FoundationArchiveService()
    set_tenant_id(tenant_id)
    try:
        async with get_db_session() as session:
            export = await dienst.export(
                session=session,
                tenant=ExportTenant(id=tenant_id, slug=slug, name=naam),
                now=moment,
                trigger=TRIGGER_SCHEMA,
            )
            try:
                await session.commit()
            except SQLAlchemyError:
                # Rij teruggedraaid, dus het pakket weg (Gate 2 ronde 2, MEDIUM-B).
                await dienst.discard(export)
                raise
    finally:
        clear_tenant_context()


async def _run_foundation_archive_exports(now: datetime | None = None) -> ArchiveRunResult:
    """Maak voor elke actieve tenant met een portaal een BagIt-archiefexport (BE-EP-054).

    Wekelijks ingepland. Een mislukte tenant houdt de andere niet tegen; aan het eind volgt wel
    een fout, zodat een gemiste export zichtbaar is in de monitoring in plaats van stil.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from src.core.services.foundation_archive_service import ArchiveExportError

    moment = now if now is not None else datetime.now(timezone.utc)
    tenants = await _foundation_portaal_tenants()
    geexporteerd = 0
    mislukt = 0
    for tenant_id, slug, naam in tenants:
        try:
            await _exporteer_archief_voor_tenant(tenant_id, slug, naam, moment)
            geexporteerd += 1
        except (ArchiveExportError, SQLAlchemyError) as e:
            # Per tenant opvangen: een tenant met een ontbrekend bestand of een databasefout
            # houdt de export van de andere tenants niet tegen (Gate 2 H1).
            mislukt += 1
            logger.error(
                "foundation_archive.export_failed tenant_id=%s: %s: %s",
                tenant_id,
                type(e).__name__,
                e,
                exc_info=True,
            )

    if mislukt:
        raise RuntimeError(
            f"archiefexport mislukt voor {mislukt} van {len(tenants)} tenant(s); zie de log"
        )
    return {"exported": geexporteerd, "failed": mislukt}


class TaggingActorResult(TypedDict):
    status: str
    content_id: int
    tags_count: int


if _DRAMATIQ_AVAILABLE:
    # Via `workflow_actor` aan de echte RedisBroker, net als de actors hierboven: een kale
    # `@dramatiq.actor` landt op de procesbrede broker die niemand uitleest (ADR-036 OP-13).
    from src.core.tasks.dramatiq_broker import workflow_actor as _foundation_actor

    @_foundation_actor(
        queue_name="default",
        max_retries=3,
        time_limit=60000,  # 1 minute
    )
    async def tag_foundation_content_async(content_id: int, tenant_id: int) -> TaggingActorResult:
        """Tag a FoundationContent item asynchronously via FoundationTaggingService."""
        from src.core.database.session import get_db_session
        from src.core.middleware.tenant_context import clear_tenant_context, set_tenant_id
        from src.core.services.foundation_tagging_service import FoundationTaggingService

        logger.info(
            "foundation_tagging.actor_start: content_id=%s, tenant_id=%s", content_id, tenant_id
        )
        set_tenant_id(tenant_id)
        try:
            async with get_db_session() as session:
                service = FoundationTaggingService()
                tags = await service.tag_content(
                    content_id=content_id,
                    tenant_id=tenant_id,
                    session=session,
                )
                await session.commit()
                return {
                    "status": "success",
                    "content_id": content_id,
                    "tags_count": len(tags),
                }
        except Exception as e:
            logger.exception(
                "foundation_tagging.actor_failed: content_id=%s, error=%s", content_id, e
            )
            raise
        finally:
            clear_tenant_context()

    @_foundation_actor(
        queue_name="maintenance",
        max_retries=0,
        time_limit=900000,  # 15 minuten: bestanden lezen en een zip bouwen per tenant
    )
    async def export_foundation_archives() -> ArchiveRunResult:
        """Wekelijkse BagIt-archiefexport voor alle portalen (BE-EP-054).

        Geen nieuwe pogingen: een herhaling zou de tenants die WEL lukten opnieuw exporteren.
        De fout komt in de log en de monitoring; de volgende week volgt een nieuwe poging.
        """
        return await _run_foundation_archive_exports()

else:
    # Testing mode: provide dummy tasks that can be mocked
    class _DummySender:
        """Dummy object with .send() method for test patching."""

        def send(self, *args: Any, **kwargs: Any) -> Any:
            logger.debug("Dummy task send called with args=%s, kwargs=%s", args, kwargs)
            return None

    run_pack_health_aggregation = _DummySender()  # pyright: ignore[reportAssignmentType]
    run_daily_maintenance = _DummySender()  # pyright: ignore[reportAssignmentType]
    run_ml_model_training = _DummySender()  # pyright: ignore[reportAssignmentType]
    run_retention_cleanup = _DummySender()  # pyright: ignore[reportAssignmentType]
    run_twin_profile_aggregation = _DummySender()  # pyright: ignore[reportAssignmentType]
    run_audit_verification = _DummySender()  # pyright: ignore[reportAssignmentType]
    cleanup_stale_tasks = _DummySender()  # pyright: ignore[reportAssignmentType]
    cleanup_expired_hitl_tickets = _DummySender()  # pyright: ignore[reportAssignmentType]
    process_document_async = _DummySender()  # pyright: ignore[reportAssignmentType]
    tag_foundation_content_async = _DummySender()  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]
    export_foundation_archives = _DummySender()  # pyright: ignore[reportAssignmentType]
