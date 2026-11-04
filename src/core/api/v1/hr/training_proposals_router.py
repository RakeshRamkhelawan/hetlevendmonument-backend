"""Opleidingsvoorstellen (HR-pilot dag 2, ADR-033 Laag 1, ADR-039).

- `POST /training-proposals` (`hr:write`): per medewerker die onder de eis zit een voorstel.
- `GET /training-proposals` (`hr:read`): de voorstellen van DEZE tenant.
- `POST /training-proposals/{id}/approve` (`hr:approve`): keurt goed en wijst de training toe via
  het bestaande pad van `schedule_training`. Vier ogen volgt de tenantinstelling voor die actie.
- `POST /training-proposals/{id}/reject` (`hr:approve`): wijst af; er wordt niets toegewezen.

BEWUST GEEN `from __future__ import annotations`: de limiet-decorators gebruiken
`functools.wraps` (zie `skills_import_router.py`).
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse
from src.core.exceptions.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    SanskritiError,
)
from src.core.utils.best_effort import best_effort

from .dependencies import (
    AuditService,
    HRTrainingProposalsRepository,
    HRTrainingScheduler,
    ProposalInputNotFound,
    _resolve_tenant_id,
    build_explanation,
    get_db,
    get_hr_training_proposals_repository,
    get_hr_training_scheduler,
    hr_import_read_limit,
    hr_import_write_limit,
    is_four_eyes_required,
    require_hr_approve,
    require_hr_read,
    require_hr_write,
)
from .schemas import TrainingProposalCreateRequest

router = APIRouter()

_ACTIE = "schedule_training"
_STATUS_VOORGESTELD = "voorgesteld"
_STATUS_GOEDGEKEURD = "goedgekeurd"
_STATUS_AFGEWEZEN = "afgewezen"
_AL_BESLIST = "Dit voorstel is al beslist."


async def _audit(
    db: AsyncSession,
    request: Request,
    current_user: UserResponse,
    *,
    event_type: str,
    omschrijving: str,
    tenant_id: int,
    proposal_id: int,
) -> None:
    # Geen e-mailadres of naam in de auditregel: alleen het nummer van het voorstel.
    async with best_effort(f"{event_type} audit log", db_session=db):
        await AuditService.log_event(
            db=db,
            event_type=event_type,
            severity="low",
            source_ip=request.client.host if request.client else "unknown",
            endpoint=str(request.url.path),
            description=omschrijving,
            tenant_id=tenant_id,
            user_id=current_user.id,
            action=event_type,
            resource=f"training_proposal:{proposal_id}",
            metadata={"proposal_id": proposal_id},
        )
        await db.commit()


@router.post("/training-proposals")
@hr_import_write_limit
async def create_training_proposals(
    request: Request,
    body: TrainingProposalCreateRequest,
    db: AsyncSession = Depends(get_db),
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    current_user: UserResponse = Depends(require_hr_write),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    try:
        uitkomst = await repo.create_from_gap(
            tenant_id,
            int(current_user.id),
            role_name=body.role_name,
            skill_name=body.skill_name,
            training_name=body.training_name,
        )
    except ProposalInputNotFound as exc:
        await db.rollback()
        raise NotFoundError("HR-gegeven", exc.soort) from exc
    try:
        await db.commit()
    except IntegrityError as exc:
        # Twee gelijktijdige verzoeken voor dezelfde functie en vaardigheid: de unieke index op
        # open voorstellen houdt de data kloppend; de tweede krijgt een nette melding.
        await db.rollback()
        raise ConflictError(
            "Er is al een voorstel voor deze medewerker en vaardigheid.",
            error_code="PROPOSAL_ALREADY_OPEN",
        ) from exc
    return {"success": True, "data": {"created": uitkomst.created, "skipped": uitkomst.skipped}}


@router.get("/training-proposals")
@hr_import_read_limit
async def list_training_proposals(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    current_user: UserResponse = Depends(require_hr_read),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    rijen = await repo.list_proposals(tenant_id, limit=limit, offset=offset)
    return {
        "success": True,
        "data": [
            {
                "id": r.id,
                "employee_email": r.employee_email,
                "skill_name": r.skill_name,
                "training_name": r.training_name,
                "reason": r.reason,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "created_by_email": r.created_by_email,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "decided_by_email": r.decided_by_email,
                # AI-verordening art. 13 en 86: bij elk voorstel de uitleg in gewone taal.
                "explanation": build_explanation(r),
            }
            for r in rijen
        ],
    }


@router.get("/training-proposals/{proposal_id}/explanation")
@hr_import_read_limit
async def get_training_proposal_explanation(
    request: Request,
    proposal_id: int,
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    current_user: UserResponse = Depends(require_hr_read),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    voorstel = await repo.get_proposal(tenant_id, proposal_id)
    if voorstel is None:
        raise NotFoundError("Opleidingsvoorstel", str(proposal_id))
    return {"success": True, "data": build_explanation(voorstel)}


@router.post("/training-proposals/{proposal_id}/approve")
@hr_import_write_limit
async def approve_training_proposal(
    request: Request,
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    wijs_toe: HRTrainingScheduler = Depends(get_hr_training_scheduler),
    current_user: UserResponse = Depends(require_hr_approve),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    voorstel = await repo.get_to_decide(tenant_id, proposal_id)
    if voorstel is None:
        raise NotFoundError("Opleidingsvoorstel", str(proposal_id))
    if voorstel.status != _STATUS_VOORGESTELD:
        raise ConflictError(_AL_BESLIST, error_code="PROPOSAL_ALREADY_DECIDED")
    # Vier ogen volgt de tenantinstelling voor `schedule_training` (ADR-039): wie het voorstel
    # maakte, keurt het dan niet zelf goed.
    if (
        await is_four_eyes_required(db, tenant_id=tenant_id, action=_ACTIE)
        and voorstel.created_by is not None
        and voorstel.created_by == current_user.id
    ):
        raise PermissionDeniedError(
            "hr:approve", f"training_proposal:{proposal_id}", str(current_user.id)
        )

    if not await repo.mark_decided(
        tenant_id, proposal_id, status=_STATUS_GOEDGEKEURD, decided_by=int(current_user.id)
    ):
        raise ConflictError(_AL_BESLIST, error_code="PROPOSAL_ALREADY_DECIDED")
    # De toewijzing commit bij succes de HELE transactie, dus de status gaat er atomair mee.
    # Bij een mislukking rolt de registry (of wij) alles terug: het voorstel blijft `voorgesteld`.
    try:
        uitkomst = await wijs_toe(tenant_id, voorstel.employee_email, voorstel.training_name)
    except Exception as exc:
        await db.rollback()
        raise SanskritiError(
            "De opleiding kon niet worden toegewezen.", error_code="HR_ASSIGN_FAILED"
        ) from exc
    if uitkomst.get("success") is not True:
        await db.rollback()
        raise ConflictError(
            "De opleiding kon niet worden toegewezen: de medewerker of de training bestaat "
            "niet meer.",
            error_code="HR_ASSIGN_FAILED",
        )
    await _audit(
        db,
        request,
        current_user,
        event_type="hr_training_proposal_approved",
        omschrijving="Opleidingsvoorstel goedgekeurd",
        tenant_id=tenant_id,
        proposal_id=proposal_id,
    )
    return {"success": True, "data": {"id": proposal_id, "status": _STATUS_GOEDGEKEURD}}


@router.post("/training-proposals/{proposal_id}/reject")
@hr_import_write_limit
async def reject_training_proposal(
    request: Request,
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    current_user: UserResponse = Depends(require_hr_approve),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    voorstel = await repo.get_to_decide(tenant_id, proposal_id)
    if voorstel is None:
        raise NotFoundError("Opleidingsvoorstel", str(proposal_id))
    if not await repo.mark_decided(
        tenant_id, proposal_id, status=_STATUS_AFGEWEZEN, decided_by=int(current_user.id)
    ):
        raise ConflictError(_AL_BESLIST, error_code="PROPOSAL_ALREADY_DECIDED")
    await db.commit()
    await _audit(
        db,
        request,
        current_user,
        event_type="hr_training_proposal_rejected",
        omschrijving="Opleidingsvoorstel afgewezen",
        tenant_id=tenant_id,
        proposal_id=proposal_id,
    )
    return {"success": True, "data": {"id": proposal_id, "status": _STATUS_AFGEWEZEN}}
