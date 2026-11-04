"""De escalatietermijn van de debiteuren lezen en wijzigen (debiteuren vanzelf afronden, B3).

Lezen mag wie debiteuren mag lezen (`receivables:read`); wijzigen alleen een tenantbeheerder, met CSRF en 10 per minuut,
en een auditregel met oud en nieuw. De tenant komt altijd uit de JWT, nooit uit het verzoek.

BEWUST GEEN `from __future__ import annotations`: zie `router.py` (rate-limit-decorators met `functools.wraps`).
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import (
    UserResponse,
    _resolve_tenant_id,
    consent_read_limit,
    consent_update_limit,
    get_current_user,
    get_db,
    lees_escalatietermijn,
    require_resource_permission,
    validate_csrf_token,
    vereis_beheerder,
    wijzig_escalatietermijn,
)

router = APIRouter(tags=["Debiteuren"])


class EscalatieTermijn(BaseModel):
    """Het aantal dagen na de verzonden brief waarna een niet-betaald dossier escaleert.

    Het bereik (1 tot en met 120) toetst de instellingenmodule met een Nederlandse melding; hier staat alleen het type.
    """

    model_config = ConfigDict(extra="forbid")

    escalatie_na_dagen: int


@router.get("/settings")
@consent_read_limit
async def get_receivable_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_resource_permission("receivables", "read")),
) -> dict[str, object]:
    """De escalatietermijn van de eigen tenant (standaard 14 dagen)."""
    termijn = await lees_escalatietermijn(db, _resolve_tenant_id(current_user))
    return {"success": True, "data": {"escalatie_na_dagen": termijn}}


@router.put("/settings", dependencies=[Depends(vereis_beheerder)])
@consent_update_limit
async def put_receivable_settings(
    request: Request,
    body: EscalatieTermijn,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Zet de escalatietermijn van de eigen tenant."""
    nieuw = await wijzig_escalatietermijn(
        db,
        tenant_id=_resolve_tenant_id(current_user),
        user_id=current_user.id,
        dagen=body.escalatie_na_dagen,
    )
    return {"success": True, "data": {"escalatie_na_dagen": nieuw}}
