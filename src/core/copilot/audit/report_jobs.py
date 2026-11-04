import logging
from datetime import datetime, timezone
from uuid import UUID

from src.core.tasks.dramatiq_broker import workflow_actor

from src.core.database.database import db_manager
from src.core.middleware.tenant_context import set_tenant_id
from src.core.utils.best_effort import best_effort
from src.core.copilot.audit.models import AuditReportJobRow
from src.core.copilot.audit.report_generator import AuditReportGenerator

logger = logging.getLogger(__name__)


@workflow_actor(queue_name="audit_reports", time_limit=1800000)  # 30 min timeout
def generate_audit_report(
    job_id: str,
    tenant_id: int,
    user_id: int,
    from_date_iso: str,
    to_date_iso: str,
    report_format: str,
) -> None:
    """Async background job to generate large audit reports."""
    logger.info(
        "Started generate_audit_report job_id=%s tenant_id=%d format=%s",
        job_id,
        tenant_id,
        report_format,
    )

    import asyncio

    asyncio.run(
        _generate_audit_report_async(
            UUID(job_id),
            tenant_id,
            user_id,
            datetime.fromisoformat(from_date_iso),
            datetime.fromisoformat(to_date_iso),
            report_format,
        )
    )


async def _generate_audit_report_async(
    job_id: UUID,
    tenant_id: int,
    user_id: int,
    from_date: datetime,
    to_date: datetime,
    report_format: str,
) -> None:
    async with db_manager.get_session() as db:
        try:
            from sqlalchemy import text

            await db.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)}
            )
            set_tenant_id(tenant_id)

            generator = AuditReportGenerator(db)

            try:
                # Mark processing
                async with best_effort("update_job_status", db_session=db):
                    job = await db.get(AuditReportJobRow, job_id)
                    if job:
                        job.status = "processing"
                        job.progress_pct = 10
                        await db.commit()

                # Generate report
                result: bytes | str
                if report_format == "pdf":
                    result = await generator.generate_pdf(job_id, tenant_id, from_date, to_date)
                else:
                    result = await generator.generate_json(job_id, tenant_id, from_date, to_date)

                result_url = f"/api/v1/copilot/audit/report/{job_id}/download"

                # Mark completed and store blob
                async with best_effort("update_job_status", db_session=db):
                    job = await db.get(AuditReportJobRow, job_id)
                    if job:
                        job.status = "completed"
                        job.progress_pct = 100
                        job.result_url = result_url
                        job.result_blob = (
                            result if isinstance(result, bytes) else result.encode("utf-8")
                        )
                        job.completed_at = datetime.now(timezone.utc)
                        await db.commit()

                logger.info("generate_audit_report completed job_id=%s", job_id)

            except Exception as exc:
                logger.error("generate_audit_report failed job_id=%s: %s", job_id, exc, exc_info=True)
                async with best_effort("update_job_status", db_session=db):
                    job = await db.get(AuditReportJobRow, job_id)
                    if job:
                        job.status = "failed"
                        await db.commit()
        finally:
            set_tenant_id(None)
