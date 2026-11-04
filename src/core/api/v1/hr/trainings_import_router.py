"""`POST /trainings/import` en `GET /trainings` (BE-AGT-060, Fase 3 dag 3, ADR-033 Laag 1).

Zelfde ontwerp als `skills_import_router.py` -- zie die module voor de onderbouwing van
`entity_type` als verzoek-niveau-discriminator, niet hier herhaald. Zelfde reden om GEEN
`from __future__ import annotations` te hebben, idem.
"""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse
from src.core.exceptions.exceptions import ConflictError
from src.core.repositories.hr_import_types import EmployeeTrainingImportRow, TrainingImportRow
from src.core.utils.best_effort import best_effort

from ._import_parsing import parse_import_file, read_upload, remap_repository_errors, validate_rows
from .dependencies import (
    AuditService,
    HRTrainingsRepository,
    _resolve_tenant_id,
    get_db,
    get_hr_trainings_import_repository,
    hr_import_read_limit,
    hr_import_write_limit,
    require_hr_read,
    require_hr_write,
)
from .schemas import (
    EmployeeTrainingImportRowSchema,
    ImportResultResponse,
    TrainingImportRowSchema,
)

router = APIRouter()

_TrainingEntityType = Literal["training", "employee_training"]


@router.post("/trainings/import")
@hr_import_write_limit
async def import_trainings_data(
    request: Request,
    entity_type: _TrainingEntityType = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    repo: HRTrainingsRepository = Depends(get_hr_trainings_import_repository),
    current_user: UserResponse = Depends(require_hr_write),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    content = await read_upload(file)
    raw_rows, row_offset = parse_import_file(content, file.content_type)

    try:
        if entity_type == "training":
            training_rows, original_indices, validation_errors = validate_rows(
                raw_rows,
                TrainingImportRowSchema,
                lambda row: TrainingImportRow(
                    name=row.name, description=row.description, skill_name=row.skill_name
                ),
                row_offset=row_offset,
            )
            outcome = await repo.upsert_trainings(tenant_id, training_rows)
        else:
            employee_training_rows, original_indices, validation_errors = validate_rows(
                raw_rows,
                EmployeeTrainingImportRowSchema,
                lambda row: EmployeeTrainingImportRow(
                    user_email=row.user_email,
                    training_name=row.training_name,
                    status=row.status,
                ),
                row_offset=row_offset,
            )
            outcome = await repo.upsert_employee_trainings(tenant_id, employee_training_rows)
    except IntegrityError as exc:
        # Zelfde race als skills_import_router.py -- zie die module's comment voor de
        # onderbouwing, niet hier herhaald.
        await db.rollback()
        raise ConflictError(
            "Gelijktijdige import gedetecteerd voor een overlappende rij -- probeer de "
            "upload opnieuw"
        ) from exc

    await db.commit()
    # AANTALLEN ALLEEN -- zelfde OP-27-redenering als skills_import_router.py.
    async with best_effort("hr trainings import audit log", db_session=db):
        await AuditService.log_event(
            db=db,
            event_type="hr_trainings_import",
            severity="low",
            source_ip=request.client.host if request.client else "unknown",
            endpoint=str(request.url.path),
            description=f"HR trainings import ({entity_type})",
            tenant_id=tenant_id,
            user_id=current_user.id,
            action=entity_type,
            metadata={
                "inserted": outcome.inserted,
                "updated": outcome.updated,
                "rejected": len(validation_errors) + len(outcome.row_errors),
            },
        )

    all_errors = sorted(
        validation_errors + remap_repository_errors(outcome.row_errors, original_indices),
        key=lambda error: error.row_index,
    )
    result = ImportResultResponse(
        inserted=outcome.inserted, updated=outcome.updated, errors=all_errors
    )
    return {"success": True, "data": result.model_dump()}


@router.get("/trainings")
@hr_import_read_limit
async def list_trainings_endpoint(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: HRTrainingsRepository = Depends(get_hr_trainings_import_repository),
    current_user: UserResponse = Depends(require_hr_read),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    trainings = await repo.list_trainings(tenant_id, limit=limit, offset=offset)
    return {
        "success": True,
        "data": [
            {
                "id": training.id,
                "name": training.name,
                "description": training.description,
                "skill_id": training.skill_id,
            }
            for training in trainings
        ],
    }
