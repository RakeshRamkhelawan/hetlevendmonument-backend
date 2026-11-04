import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
import os
from fastapi.responses import JSONResponse

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.auth.runtime_deps import UserResponse, get_current_user, is_tenant_admin
from src.core.copilot.api.contest_service import submit_contest
from src.core.copilot.api.explanation_builder import build_explanation
from src.core.copilot.audit.report_generator import AuditReportGenerator
from src.core.copilot.audit.models import AuditReportJobRow
from src.core.copilot.audit.report_jobs import generate_audit_report
from src.core.copilot.api.schemas import (
    ChainVerifyResponse,
    ContestRequest,
    ContestResolveRequest,
    ContestResponse,
    DecisionExplanationResponse,
)
from src.core.copilot.council.contest_models import DecisionContestRow
from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.database.database import get_db
from src.core.governance.audit import AuditService
from src.domains.notifications.models import Notification
from src.core.shared.rate_limiter import (
    ai_transparency_limit,
    consent_update_limit,
)
from src.core.middleware.tenant_context import require_tenant_id
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

router = APIRouter()


async def _set_rls_tenant(db: AsyncSession, tenant_id: int) -> None:
    """Set RLS tenant context using parameterized SQL (no f-string)."""
    await db.execute(
        text("SELECT set_config('app.current_tenant', :t, true)"),
        {"t": str(tenant_id)},
    )


#: Canoniek in `src/core/auth/dependencies.py` -- deze naam blijft als alias, want hij wordt in
#: dit bestand en in tests aangeroepen. Zie ADR-036 OP-31: er waren twee identieke kopieen en er
#: was een derde nodig; dat is nu een consolidatie geworden.
_is_tenant_admin = is_tenant_admin


# NOTE: Static routes MUST be defined BEFORE dynamic /{decision_id} routes,
# otherwise FastAPI matches /verify and /report as decision_id UUIDs.


@router.get(
    "/verify",
    response_model=ChainVerifyResponse,
    summary="Verify hash chain integrity (admin only)",
)
@ai_transparency_limit
async def verify_chain(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> ChainVerifyResponse:
    if not _is_tenant_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    await _set_rls_tenant(db, tenant_id)

    logger.info(
        "verify_chain started",
        extra={"tenant_id": tenant_id, "user_id": current_user.id},
    )

    # NOTE: For very large tenants (>100k decisions) this is too slow for a
    # synchronous response. Post-MVP: move to async job with progress polling.
    try:
        result = await db.execute(
            select(CouncilDecisionRow)
            .where(CouncilDecisionRow.tenant_id == tenant_id)
            .order_by(CouncilDecisionRow.timestamp.asc())
        )
        rows = result.scalars().all()
    except Exception as exc:
        logger.error(
            "verify_chain query failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        ) from exc

    broken_links: list[UUID] = []
    previous_hash: str | None = None
    for row in rows:
        if previous_hash is not None and row.previous_decision_hash != previous_hash:
            broken_links.append(row.decision_id)
        previous_hash = row.decision_hash

    return ChainVerifyResponse(
        chain_valid=not broken_links,
        decisions_checked=len(rows),
        broken_links=broken_links,
        checked_at=datetime.now(timezone.utc),
        tenant_id=tenant_id,
    )


from typing import Literal


async def _start_rapportopdracht(
    db: AsyncSession,
    job_id: UUID,
    tenant_id: int,
    user_id: int,
    from_date: datetime,
    to_date: datetime,
    format: str,
) -> None:
    """Zet de rapportopdracht in de wachtrij; lukt dat niet, dan een 503 en een opdracht op "failed".

    De opdracht staat op dat moment al op "pending" in de database. Zonder deze afvang bleef hij daar voor altijd
    staan (ADR-036 OP-13: sinds de echte broker faalt `.send()` zichtbaar als Redis weg is).
    """
    try:
        generate_audit_report.send(
            str(job_id),
            tenant_id,
            user_id,
            from_date.isoformat(),
            to_date.isoformat(),
            format,
        )
    except Exception as exc:
        logger.error(
            "Auditrapport %s niet verstuurd naar de werker: %s: %s",
            job_id,
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        async with best_effort("auditrapportopdracht op failed zetten", db_session=db):
            job = await db.get(AuditReportJobRow, job_id)
            if job is not None:
                job.status = "failed"
                await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Het rapport is niet gestart: de opdracht kon niet naar de werker. "
                "Probeer het over enkele minuten opnieuw."
            ),
        ) from exc


@router.get(
    "/report",
    summary="Audit report (admin only)",
)
@ai_transparency_limit
async def get_audit_report(
    request: Request,
    from_date: datetime = Query(..., alias="from"),
    to_date: datetime = Query(..., alias="to"),
    format: Literal["json", "pdf"] = Query("json"),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> Response:
    if not _is_tenant_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    if (to_date - from_date) > timedelta(days=400):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Range max 400 days",
        )

    await _set_rls_tenant(db, tenant_id)

    logger.info(
        "get_audit_report started",
        extra={"tenant_id": tenant_id, "user_id": current_user.id},
    )

    try:
        count = await db.scalar(
            select(func.count())
            .select_from(CouncilDecisionRow)
            .where(
                CouncilDecisionRow.tenant_id == tenant_id,
                CouncilDecisionRow.timestamp >= from_date,
                CouncilDecisionRow.timestamp <= to_date,
            )
        )
    except Exception as exc:
        logger.error("Failed to count decisions: %s", exc)
        raise HTTPException(status_code=500, detail="Internal error")

    threshold = int(os.getenv("AUDIT_REPORT_ASYNC_THRESHOLD", "10000"))

    if count and count > threshold:
        import uuid

        job_id = uuid.uuid4()

        async with best_effort("create_audit_job", db_session=db):
            job = AuditReportJobRow(
                job_id=job_id,
                tenant_id=tenant_id,
                user_id=current_user.id,
                status="pending",
                from_date=from_date,
                to_date=to_date,
                format=format,
                created_at=datetime.now(timezone.utc),
            )
            db.add(job)
            await db.commit()

        await _start_rapportopdracht(
            db=db,
            job_id=job_id,
            tenant_id=tenant_id,
            user_id=current_user.id,
            from_date=from_date,
            to_date=to_date,
            format=format,
        )

        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "message": "Report generation started",
                "job_id": str(job_id),
                "status_url": f"/api/v1/copilot/audit/report/{job_id}/status",
            },
        )

    # Synchronous flow for small reports
    generator = AuditReportGenerator(db)
    job_id_sync = UUID(int=0)  # Dummy ID for sync

    try:
        if format == "json":
            result = await generator.generate_json(job_id_sync, tenant_id, from_date, to_date)
            return Response(content=result, media_type="application/json")

        pdf_bytes = await generator.generate_pdf(job_id_sync, tenant_id, from_date, to_date)
        filename = f'attachment; filename="audit-report-{tenant_id}-{from_date.date()}-{to_date.date()}.pdf"'
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": filename},
        )
    except Exception as exc:
        logger.error("Report generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/report/{job_id}/status", summary="Check async report status")
@ai_transparency_limit
async def get_report_status(
    request: Request,
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not _is_tenant_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")

    await _set_rls_tenant(db, tenant_id)

    job = await db.get(AuditReportJobRow, job_id)
    if not job or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(job.job_id),
        "status": job.status,
        "progress_pct": job.progress_pct,
        "result_url": job.result_url,
    }


@router.get("/report/{job_id}/download", summary="Download async report result")
@ai_transparency_limit
async def download_report(
    request: Request,
    job_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> Response:
    if not _is_tenant_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")

    await _set_rls_tenant(db, tenant_id)

    job = await db.get(AuditReportJobRow, job_id)
    if not job or job.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not completed")

    if not job.result_blob:
        raise HTTPException(status_code=404, detail="File content missing")

    media_type = "application/pdf" if job.format == "pdf" else "application/json"
    filename = f"audit-report-{tenant_id}.{job.format}"

    return Response(
        content=job.result_blob,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/contests", summary="Contest admin queue (GDPR art. 22, admin only)")
@ai_transparency_limit
async def list_contests(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not _is_tenant_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    await _set_rls_tenant(db, tenant_id)

    total = await db.scalar(
        select(func.count())
        .select_from(DecisionContestRow)
        .where(DecisionContestRow.tenant_id == tenant_id)
    )
    result = await db.execute(
        select(DecisionContestRow)
        .where(DecisionContestRow.tenant_id == tenant_id)
        .order_by(DecisionContestRow.submitted_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    data = [
        {
            "contest_id": str(r.contest_id),
            "decision_id": str(r.decision_id),
            "user_id": r.user_id,
            "status": r.status,
            "reason_category": r.reason_category,
            "reason_text": r.reason_text,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "resolution_text": r.resolution_text,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "resolver_user_id": r.resolver_user_id,
        }
        for r in rows
    ]
    return {"success": True, "data": data, "total": int(total or 0)}


@router.post("/contests/{contest_id}/resolve", summary="Resolve a contest (admin only)")
@consent_update_limit
async def resolve_contest(
    request: Request,
    contest_id: UUID,
    body: ContestResolveRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if not _is_tenant_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")

    await _set_rls_tenant(db, tenant_id)

    result = await db.execute(
        select(DecisionContestRow).where(
            DecisionContestRow.contest_id == contest_id,
            DecisionContestRow.tenant_id == tenant_id,
        )
    )
    contest = result.scalar_one_or_none()
    if contest is None:
        # Identical message cross-tenant to avoid contest-id enumeration.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")
    if contest.status != "pending":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Contest already resolved")

    contest.status = body.status
    contest.resolution_text = body.resolution_text
    contest.resolved_at = datetime.now(timezone.utc)
    contest.resolver_user_id = current_user.id
    await db.commit()

    # Real notification to the submitter (GDPR art. 22 -- no stub).
    async with best_effort("contest resolve notify", db_session=db):
        db.add(
            Notification(
                tenant_id=tenant_id,
                user_id=contest.user_id,
                type="contest_resolved",
                title="Your contest has been resolved",
                body=f"Status: {body.status}",
                data={
                    "contest_id": str(contest.contest_id),
                    "decision_id": str(contest.decision_id),
                    "status": body.status,
                },
            )
        )
        await db.commit()

    # ADR-019 tamper-evident audit entry via AuditService (computes + chains audit_hash).
    # best_effort: primary data (the resolution) is already committed above.
    async with best_effort("contest resolve audit", db_session=db):
        await AuditService.log_action(
            tenant_id=tenant_id,
            action="contest_resolved",
            resource=f"contest:{contest.contest_id}",
            user_id=current_user.id,
            threat_level="low",
            endpoint="/copilot/audit/contests/resolve",
            event_type="governance",
            description=(
                f"Admin {current_user.id} resolved contest {contest.contest_id} as {body.status}"
            ),
            details={"contest_id": str(contest.contest_id), "status": body.status},
            session=db,
        )
        await db.commit()

    resolved_at = contest.resolved_at
    return {
        "success": True,
        "contest_id": str(contest.contest_id),
        "status": contest.status,
        "resolved_at": resolved_at.isoformat() if resolved_at else None,
    }


@router.get(
    "/{decision_id}",
    response_model=DecisionExplanationResponse,
    summary="Right-to-explanation for an AI decision (GDPR art. 13-15)",
)
@ai_transparency_limit
async def get_decision_explanation(
    request: Request,
    decision_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
) -> DecisionExplanationResponse:
    await _set_rls_tenant(db, tenant_id)

    logger.info(
        "get_decision_explanation started",
        extra={"tenant_id": tenant_id, "user_id": current_user.id},
    )

    try:
        result = await db.execute(
            select(CouncilDecisionRow).where(
                CouncilDecisionRow.decision_id == decision_id,
                CouncilDecisionRow.tenant_id == tenant_id,
            )
        )
        decision = result.scalar_one_or_none()
    except Exception as exc:
        logger.error(
            "get_decision_explanation query failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        ) from exc

    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Decision not found",
        )

    is_admin = _is_tenant_admin(current_user)
    if decision.user_id != current_user.id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Decision not accessible",
        )

    verdicts_result = await db.execute(
        select(OfficerVerdictRow)
        .where(
            OfficerVerdictRow.decision_id == decision.decision_id,
            OfficerVerdictRow.tenant_id == tenant_id,
        )
        .order_by(OfficerVerdictRow.officer_name)
    )
    verdicts = verdicts_result.scalars().all()

    # Audit-trail of the explanation request itself (GDPR art. 22), tamper-evident via
    # AuditService (ADR-019 hash-chain) -- not a raw NULL-hash INSERT.
    async with best_effort("audit explanation request", db_session=db):
        await AuditService.log_action(
            tenant_id=tenant_id,
            action="explanation_requested",
            resource=f"decision:{decision_id}",
            user_id=current_user.id,
            threat_level="low",
            endpoint="/copilot/audit/{decision_id}",
            event_type="governance",
            description=f"User {current_user.id} requested explanation for decision {decision_id}",
            details={"decision_id": str(decision_id)},
            session=db,
        )
        await db.commit()

    return build_explanation(
        decision=decision,
        verdicts=list(verdicts),
        language=None,
        viewing_user=current_user,
    )


@router.post(
    "/{decision_id}/contest",
    response_model=ContestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Contest a decision (GDPR art. 22)",
)
@consent_update_limit
async def contest_decision(
    request: Request,
    decision_id: UUID,
    body: ContestRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    _csrf: None = Depends(validate_csrf_token),
) -> ContestResponse:
    await _set_rls_tenant(db, tenant_id)

    logger.info(
        "contest_decision started",
        extra={"tenant_id": tenant_id, "user_id": current_user.id},
    )

    try:
        result = await db.execute(
            select(CouncilDecisionRow).where(
                CouncilDecisionRow.decision_id == decision_id,
                CouncilDecisionRow.tenant_id == tenant_id,
            )
        )
        decision = result.scalar_one_or_none()
    except Exception as exc:
        logger.error(
            "contest_decision query failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        ) from exc

    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Decision not found",
        )

    is_admin = _is_tenant_admin(current_user)
    if decision.user_id != current_user.id and not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Decision not accessible",
        )

    try:
        contest = await submit_contest(
            db=db,
            decision=decision,
            user=current_user,
            reason_category=body.reason_category,
            reason_text=body.reason_text,
        )
    except Exception as exc:
        logger.error(
            "submit_contest failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error",
        ) from exc

    melding_mislukt = contest.admin_notification == "mislukt"
    return ContestResponse(
        contest_id=contest.contest_id,
        status=contest.status,
        submitted_at=contest.submitted_at,
        expected_review_within_hours=72,
        admin_notification="mislukt" if melding_mislukt else "verzonden",
        message=(
            "Uw bezwaar is bewaard. De melding aan de beheerders is niet verstuurd; zij zien uw "
            "bezwaar pas bij hun eerstvolgende controle."
            if melding_mislukt
            else None
        ),
    )
