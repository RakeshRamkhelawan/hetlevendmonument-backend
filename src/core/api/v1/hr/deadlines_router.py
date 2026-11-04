"""Termijnen (HR-pilot dag 3, ADR-033 Laag 1, ADR-039).

- `POST /deadlines` (`hr:write`): een termijn vastleggen (het formulier).
- `POST /deadlines/import` (`hr:write`): dezelfde regels uit een CSV-bestand.
- `PATCH /deadlines/{id}` (`hr:write`): afronden of de datum van de probleemanalyse invullen.
- `GET /deadlines/upcoming` (`hr:read`): "Komende termijnen", BEREKEND uit de ingevulde data.

Het systeem beslist niets: het toont wanneer iets uiterlijk moet en waar de regel vandaan komt.
Verzuim is een gezondheidsgegeven: alleen `hr:read` ziet het, er wordt GEEN omschrijving bij
bewaard en de auditregel bevat geen namen of e-mailadressen.

BEWUST GEEN `from __future__ import annotations`: de limiet-decorators gebruiken
`functools.wraps` (zie `skills_import_router.py`).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse
from src.core.exceptions.exceptions import NotFoundError, ValidationError
from src.core.utils.best_effort import best_effort

from ._import_parsing import parse_import_file, read_upload, remap_repository_errors, validate_rows
from .dependencies import (
    AnalysisBeforeStart,
    AuditService,
    DeadlineInput,
    HRDeadlinesRepository,
    UnknownEmployee,
    _resolve_tenant_id,
    get_db,
    get_hr_deadlines_repository,
    hr_import_read_limit,
    hr_import_write_limit,
    require_hr_read,
    require_hr_write,
)
from .schemas import (
    DeadlineCreateRequest,
    DeadlineImportRowSchema,
    DeadlineUpdateRequest,
    ImportResultResponse,
)

router = APIRouter()


async def _audit(
    db: AsyncSession,
    request: Request,
    current_user: UserResponse,
    *,
    event_type: str,
    omschrijving: str,
    tenant_id: int,
    metadata: dict[str, object],
) -> None:
    # Alleen nummers en aantallen: geen e-mailadres, geen omschrijving, geen soort verzuim-data.
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
            metadata=metadata,
        )
        await db.commit()


@router.post("/deadlines")
@hr_import_write_limit
async def create_deadline(
    request: Request,
    body: DeadlineCreateRequest,
    db: AsyncSession = Depends(get_db),
    repo: HRDeadlinesRepository = Depends(get_hr_deadlines_repository),
    current_user: UserResponse = Depends(require_hr_write),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    try:
        deadline_id = await repo.add(
            tenant_id,
            int(current_user.id),
            DeadlineInput(
                user_email=body.user_email,
                kind=body.kind,
                start_date=body.start_date,
                end_date=body.end_date,
                analysis_date=body.analysis_date,
                description=body.description,
            ),
        )
    except UnknownEmployee as exc:
        await db.rollback()
        raise NotFoundError("Medewerker") from exc
    await db.commit()
    await _audit(
        db,
        request,
        current_user,
        event_type="hr_deadline_created",
        omschrijving="Termijn vastgelegd",
        tenant_id=tenant_id,
        metadata={"deadline_id": deadline_id, "kind": body.kind},
    )
    return {"success": True, "data": {"id": deadline_id}}


@router.post("/deadlines/import")
@hr_import_write_limit
async def import_deadlines(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    repo: HRDeadlinesRepository = Depends(get_hr_deadlines_repository),
    current_user: UserResponse = Depends(require_hr_write),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    content = await read_upload(file)
    raw_rows, row_offset = parse_import_file(content, file.content_type)
    rijen, originele_nummers, validatiefouten = validate_rows(
        raw_rows,
        DeadlineImportRowSchema,
        lambda r: DeadlineInput(
            user_email=r.user_email,
            kind=r.kind,
            start_date=r.start_date,
            end_date=r.end_date,
            analysis_date=r.analysis_date,
            description=r.description,
        ),
        row_offset=row_offset,
    )
    aantal, repo_fouten = await repo.add_many(tenant_id, int(current_user.id), rijen)
    await db.commit()
    await _audit(
        db,
        request,
        current_user,
        event_type="hr_deadlines_import",
        omschrijving="Termijnen ingelezen uit een bestand",
        tenant_id=tenant_id,
        metadata={"inserted": aantal, "rejected": len(validatiefouten) + len(repo_fouten)},
    )
    alle_fouten = sorted(
        validatiefouten + remap_repository_errors(repo_fouten, originele_nummers),
        key=lambda fout: fout.row_index,
    )
    resultaat = ImportResultResponse(inserted=aantal, updated=0, errors=alle_fouten)
    return {"success": True, "data": resultaat.model_dump()}


@router.patch("/deadlines/{deadline_id}")
@hr_import_write_limit
async def update_deadline(
    request: Request,
    deadline_id: int,
    body: DeadlineUpdateRequest,
    db: AsyncSession = Depends(get_db),
    repo: HRDeadlinesRepository = Depends(get_hr_deadlines_repository),
    current_user: UserResponse = Depends(require_hr_write),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    try:
        gevonden = await repo.update(
            tenant_id,
            deadline_id,
            status=body.status,
            analysis_date=body.analysis_date,
            done_label=body.done_label,
        )
    except AnalysisBeforeStart as exc:
        await db.rollback()
        raise ValidationError(
            "De probleemanalyse kan niet voor de eerste ziektedag liggen.",
            error_code="ANALYSIS_BEFORE_START",
        ) from exc
    if not gevonden:
        await db.rollback()
        raise NotFoundError("Termijn", str(deadline_id))
    await db.commit()
    await _audit(
        db,
        request,
        current_user,
        event_type="hr_deadline_updated",
        omschrijving="Termijn gewijzigd",
        tenant_id=tenant_id,
        metadata={"deadline_id": deadline_id},
    )
    return {"success": True, "data": {"id": deadline_id}}


@router.get("/deadlines/upcoming")
@hr_import_read_limit
async def list_upcoming_deadlines(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: HRDeadlinesRepository = Depends(get_hr_deadlines_repository),
    current_user: UserResponse = Depends(require_hr_read),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    vandaag = datetime.now(timezone.utc).date()
    items = await repo.upcoming(tenant_id, vandaag)
    return {
        "success": True,
        "data": [
            {
                "deadline_id": i.deadline_id,
                "employee_email": i.employee_email,
                "kind": i.kind,
                "label": i.label,
                "date": i.datum.isoformat(),
                "bron": i.bron,
                "toelichting": i.toelichting,
                "te_laat": i.te_laat,
                "description": i.description,
            }
            for i in items[offset : offset + limit]
        ],
    }
