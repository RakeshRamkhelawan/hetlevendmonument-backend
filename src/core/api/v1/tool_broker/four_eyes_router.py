"""Vier ogen per actie lezen en wijzigen (ADR-039, debiteurenagent dag 3).

Naast de HITL-router, omdat dit de instelling is die daar bij goedkeuren wordt gelezen
(`_refuse_self_approval`). Lezen mag iedereen van de tenant: wie een verzoek indient, moet kunnen
zien of hij het zelf mag beslissen. Wijzigen is een beheerhandeling (ADR-039 laag 2): alleen een
tenantbeheerder, met CSRF, 10 per minuut, en een auditregel met de uitvoerder en oude en nieuwe
waarde. De tenant komt altijd uit de JWT.

BEWUST GEEN `from __future__ import annotations`: zie `hitl_router.py` (rate-limit-decorators en
FastAPI-bodymodellen).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.tool_broker.dependencies import (
    AuditService,
    confirm_four_eyes_explanation,
    consent_read_limit,
    consent_update_limit,
    get_db,
    read_explanation_pending,
    read_four_eyes_actions,
    write_four_eyes_actions,
)
# Gebruiker en beheerdersvraag via de admin-facade, zoals `receivables/dependencies.py`: geen
# nieuw paar van dit bestand naar `auth` (fan-out-budget `test_dsm_grade_a_plus.py`, 557).
from src.core.api.v1.admin.dependencies import UserResponse, get_current_user, require_admin_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/tools/hitl", tags=["Tool Broker HITL"])


class FourEyesUpdate(BaseModel):
    """De volledige lijst acties waarvoor vier ogen AAN moet staan."""

    actions: list[str] = Field(default_factory=list, max_length=50)


#: De rolcontrole voor de twee schrijfroutes. `require_admin_role` delegeert naar `is_admin`, wat
#: ook `is_tenant_admin` (de goedkeurgrens in `hitl_router._require_approver`) aanroept: dezelfde
#: groep mag beslissen en de instelling wijzigen. Als dependency komt de 403 voor de validatie
#: van de body (plan nazorg, punt d).
_ALLEEN_BEHEERDER = [Depends(require_admin_role)]


@router.get("/four-eyes")
@consent_read_limit
async def get_four_eyes(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, object]:
    """Per actie: staat vier ogen aan in de eigen tenant? En moet de uitleg nog getoond worden?"""
    return {"success": True, "data": await _stand(db, current_user.tenant_id)}


async def _stand(db: AsyncSession, tenant_id: int) -> dict[str, object]:
    return {
        "actions": await read_four_eyes_actions(db, tenant_id=tenant_id),
        "explanation_pending": await read_explanation_pending(db, tenant_id=tenant_id),
    }


@router.post("/four-eyes/explanation-confirmed", dependencies=_ALLEEN_BEHEERDER)
@consent_update_limit
async def confirm_four_eyes_explanation_route(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """De beheerder heeft de uitleg gezien en de keuzes bevestigd (ADR-039, "Bestaande ondernemingen")."""
    try:
        stond_er = await confirm_four_eyes_explanation(db, tenant_id=current_user.tenant_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found") from exc

    from src.core.utils.best_effort import best_effort

    client_host = request.client.host if request.client else "unknown"
    async with best_effort("ADR-039 auditregel vier-ogen-uitleg bevestigd", db_session=db):
        await AuditService.log_event(
            db=db,
            event_type="four_eyes_explanation_confirmed",
            severity="low",
            source_ip=client_host,
            endpoint=request.url.path,
            description=f"Four-eyes explanation confirmed by user {current_user.id}",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="update",
            metadata={"was_pending": stond_er},
        )
        await db.commit()

    return {"success": True, "data": await _stand(db, current_user.tenant_id)}


@router.put("/four-eyes", dependencies=_ALLEEN_BEHEERDER)
@consent_update_limit
async def put_four_eyes(
    request: Request,
    body: FourEyesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Zet vier ogen aan voor precies de meegegeven acties, uit voor de rest."""
    try:
        oud, nieuw = await write_four_eyes_actions(
            db, tenant_id=current_user.tenant_id, actions=body.actions
        )
    except ValueError as exc:
        # Geen invoer terug in de melding: alleen dat er een onbekende naam bij zat.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown action in the list"
        ) from exc
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found") from exc

    from src.core.utils.best_effort import best_effort

    client_host = request.client.host if request.client else "unknown"
    async with best_effort("ADR-039 auditregel vier-ogen-instelling", db_session=db):
        await AuditService.log_event(
            db=db,
            event_type="four_eyes_settings_changed",
            severity="medium",
            source_ip=client_host,
            endpoint=request.url.path,
            description=f"Four-eyes setting changed by user {current_user.id}",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="update",
            metadata={"old": oud, "new": nieuw},
        )
        await db.commit()

    return {"success": True, "data": await _stand(db, current_user.tenant_id)}
