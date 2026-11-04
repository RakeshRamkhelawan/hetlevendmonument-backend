"""De opleidingsvoorstellen van de medewerker ZELF (AI-verordening art. 86, ADR-033 Laag 1).

- `GET /my-training-proposals`: alleen de voorstellen van de aanroeper, elk met een uitleg.
- `GET /my-training-proposals/{id}/explanation`: de uitleg van een eigen voorstel; een voorstel van
  een collega of van een andere tenant is hier gewoon "niet gevonden" (404), nooit 403: een 403
  zou verklappen dat het voorstel bestaat.

Inloggen is genoeg: dit is geen HR-recht (`hr:read`) maar het recht om te weten wat er over jezelf
is voorgesteld. De medewerker komt uit de JWT (`current_user.id`), de tenant uit de JWT-context;
beide komen NOOIT uit het verzoek. De uitleg bevat geen e-mailadres van een collega, ook niet van
degene die besliste.

BEWUST GEEN `from __future__ import annotations`: de limiet-decorators gebruiken
`functools.wraps` (zie `skills_import_router.py`).
"""

from fastapi import APIRouter, Depends, Query, Request

from src.core.exceptions.exceptions import NotFoundError

from .dependencies import (
    HRTrainingProposalsRepository,
    UserResponse,
    _resolve_tenant_id,
    build_explanation,
    get_current_user,
    get_hr_training_proposals_repository,
    hr_import_read_limit,
)

router = APIRouter()


@router.get("/my-training-proposals")
@hr_import_read_limit
async def list_my_training_proposals(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    rijen = await repo.list_for_user(tenant_id, int(current_user.id), limit=limit, offset=offset)
    return {
        "success": True,
        "data": [
            {
                "id": r.id,
                "skill_name": r.skill_name,
                "training_name": r.training_name,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "explanation": build_explanation(r, voor_medewerker=True),
            }
            for r in rijen
        ],
    }


@router.get("/my-training-proposals/{proposal_id}/explanation")
@hr_import_read_limit
async def get_my_training_proposal_explanation(
    request: Request,
    proposal_id: int,
    repo: HRTrainingProposalsRepository = Depends(get_hr_training_proposals_repository),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    voorstel = await repo.get_for_user(tenant_id, int(current_user.id), proposal_id)
    if voorstel is None:
        raise NotFoundError("Opleidingsvoorstel", str(proposal_id))
    return {"success": True, "data": build_explanation(voorstel, voor_medewerker=True)}
