"""`POST /skills/import` en `GET /skills` (BE-AGT-060, Fase 3 dag 3, ADR-033 Laag 1).

`entity_type` (formveld) selecteert het rijschema voor het HELE verzoek, niet per rij -- een
gemengd CSV-bestand met verschillende rijvormen is geen realistisch HR-exportformaat, en een
per-rij-discriminator zou dezelfde complexiteit hebben als drie losse endpoints met een
slechtere foutlocalisatie.

BEWUST GEEN `from __future__ import annotations`: `@hr_import_write_limit`/`@hr_import_read_
limit` gebruiken `functools.wraps`, en die combinatie met lazy-gestringificeerde annotaties
laat FastAPI's `Form(...)`-parameter-resolutie stuklopen (422/PydanticUserError op de
`Literal`-forward-reference) -- exact de bekende valkuil, empirisch bevestigd tijdens het
schrijven van de tests hier.
"""

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse
from src.core.exceptions.exceptions import ConflictError, SanskritiError
from src.core.repositories.hr_import_types import (
    EmployeeAssessmentImportRow,
    RoleRequirementImportRow,
    SkillImportRow,
)
from src.core.utils.best_effort import best_effort

from ._import_parsing import parse_import_file, read_upload, remap_repository_errors, validate_rows
from .dependencies import (
    AuditService,
    HRGapReader,
    HRSkillsImportRepository,
    _resolve_tenant_id,
    get_db,
    get_hr_gap_reader,
    get_hr_skills_import_repository,
    hr_import_read_limit,
    hr_import_write_limit,
    require_hr_read,
    require_hr_write,
)
from .schemas import (
    EmployeeAssessmentImportRowSchema,
    ImportResultResponse,
    RoleRequirementImportRowSchema,
    SkillImportRowSchema,
)

router = APIRouter()

_SkillEntityType = Literal["skill", "role_requirement", "employee_assessment"]


@router.post("/skills/import")
@hr_import_write_limit
async def import_skills_data(
    request: Request,
    entity_type: _SkillEntityType = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    repo: HRSkillsImportRepository = Depends(get_hr_skills_import_repository),
    current_user: UserResponse = Depends(require_hr_write),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    content = await read_upload(file)
    raw_rows, row_offset = parse_import_file(content, file.content_type)

    try:
        if entity_type == "skill":
            skill_rows, original_indices, validation_errors = validate_rows(
                raw_rows,
                SkillImportRowSchema,
                lambda row: SkillImportRow(name=row.name, category=row.category),
                row_offset=row_offset,
            )
            outcome = await repo.upsert_skills(tenant_id, skill_rows)
        elif entity_type == "role_requirement":
            role_requirement_rows, original_indices, validation_errors = validate_rows(
                raw_rows,
                RoleRequirementImportRowSchema,
                lambda row: RoleRequirementImportRow(
                    role_name=row.role_name,
                    skill_name=row.skill_name,
                    required_level=row.required_level,
                ),
                row_offset=row_offset,
            )
            outcome = await repo.upsert_role_requirements(tenant_id, role_requirement_rows)
        else:
            employee_assessment_rows, original_indices, validation_errors = validate_rows(
                raw_rows,
                EmployeeAssessmentImportRowSchema,
                lambda row: EmployeeAssessmentImportRow(
                    user_email=row.user_email, skill_name=row.skill_name, level=row.level
                ),
                row_offset=row_offset,
            )
            outcome = await repo.upsert_employee_assessments(tenant_id, employee_assessment_rows)
    except IntegrityError as exc:
        # Check-then-insert-race tussen twee gelijktijdige imports met een overlappende
        # sleutel (bv. dezelfde nieuwe skill-naam) -- Dag 2 liet dit expliciet aan Dag 3 over
        # (final-approver-fase3-dag-2.md) i.p.v. een onafgevangen 500 te laten doorschieten.
        await db.rollback()
        raise ConflictError(
            "Gelijktijdige import gedetecteerd voor een overlappende rij -- probeer de "
            "upload opnieuw"
        ) from exc

    await db.commit()
    # AANTALLEN ALLEEN -- nooit ruwe rijinhoud/e-mailadressen in de audit-log (zelfde
    # OP-27-redenering als hr_registry.py's analyze_skill_gap toepast op zijn output).
    async with best_effort("hr skills import audit log", db_session=db):
        await AuditService.log_event(
            db=db,
            event_type="hr_skills_import",
            severity="low",
            source_ip=request.client.host if request.client else "unknown",
            endpoint=str(request.url.path),
            description=f"HR skills import ({entity_type})",
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


@router.get("/skills")
@hr_import_read_limit
async def list_skills_endpoint(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: HRSkillsImportRepository = Depends(get_hr_skills_import_repository),
    current_user: UserResponse = Depends(require_hr_read),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    skills = await repo.list_skills(tenant_id, limit=limit, offset=offset)
    return {
        "success": True,
        "data": [
            {"id": skill.id, "name": skill.name, "category": skill.category} for skill in skills
        ],
    }


@router.get("/skills/gap")
@hr_import_read_limit
async def skill_gap_endpoint(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    lees_kloof: HRGapReader = Depends(get_hr_gap_reader),
    current_user: UserResponse = Depends(require_hr_read),
) -> dict[str, object]:
    """Per functie en vaardigheid: hoeveel mensen voldoen, hoeveel niet, hoeveel niet beoordeeld."""
    tenant_id = _resolve_tenant_id(current_user)
    uitkomst = await lees_kloof(tenant_id, limit, offset)
    if uitkomst.get("success") is not True:
        raise SanskritiError("De kloofanalyse is mislukt.", error_code="HR_GAP_FAILED")
    return {"success": True, "data": uitkomst}
