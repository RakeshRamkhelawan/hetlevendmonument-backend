"""AVG-wissing plannen en intrekken: een medewerker wissen en delete-all intrekken (GDPR art. 17).

Besluit Rakesh 2026-10-12: een wissing wacht 30 dagen en is binnen die tijd in te trekken; de
werkgever kan EEN medewerker laten wissen. Niets wordt hier gewist: de betrokkene wordt inactief en
`users.deletion_scheduled_for` krijgt de datum; de dagelijkse planner
(`src/core/jobs/avg_purge_job.py`) plant de purge pas daarna in. Zie
`src/core/governance/avg_wissing_planning.py`.

- `POST /api/gdpr/users/{user_id}/erase`          plan de wissing van een medewerker
- `POST /api/gdpr/users/{user_id}/erase/revoke`   trek die aanvraag in
- `POST /api/gdpr/delete-all/revoke`              trek een tenantbrede wissing in
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:  # alleen voor de annotatie: een runtime-import telt als DSM-koppeling
    from src.core.models.rbac_models import User

from .dependencies import (
    AuditLog,
    AuditService,
    C7Workflow as Workflow,
    UserResponse,
    eigen_gebruiker,
    eis_dat_gebruiker_uitgeschakeld_mag_worden,
    gebruikers_met_geplande_wissing,
    get_current_tenant_id,
    get_current_user,
    get_db,
    is_door_aanvraag_inactief,
    is_laatste_beheerder,
    lopende_delete_all,
    meld_tenant_zonder_beheerder,
    plan_gebruiker_wissing,
    require_user_manager_eigen_tenant,
    termijn_is_verstreken,
    trek_gebruiker_wissing_in,
)
from .schemas import EraseUserResponse, RevokeResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/gdpr", tags=["GDPR Compliance"])

_TERMIJN_VERSTREKEN = "De termijn van 30 dagen is verstreken; intrekken kan niet meer"


async def _schrijf_audit(
    db: AsyncSession,
    tenant_id: int,
    actor_id: int,
    action: str,
    resource: str,
    details: dict[str, object],
) -> None:
    """Auditregel met alleen nummers, geen persoonsgegevens; mislukt hij, dan blijft de wijziging."""
    try:
        await AuditService.log_action(
            tenant_id=tenant_id,
            action=action,
            resource=resource,
            user_id=actor_id,
            details=details,
            session=db,
            event_type="gdpr_delete",
            threat_level="warning",
            client_ip="unknown",
            endpoint="/api/gdpr",
            description=f"AVG-wissing: {action}",
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(
            "gdpr wissing audit mislukt (%s): %s: %s",
            action,
            type(exc).__name__,
            exc,
            exc_info=True,
        )


async def _eigen_gebruiker(db: AsyncSession, tenant_id: int, user_id: int) -> "User":
    gebruiker = await eigen_gebruiker(db, tenant_id, user_id)
    if gebruiker is None:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden")
    return gebruiker


@router.post(
    "/users/{user_id}/erase",
    response_model=EraseUserResponse,
    summary="Laat de gegevens van een medewerker wissen (AVG art. 17), na 30 dagen",
)
async def request_user_erase(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_user_manager_eigen_tenant),
    tenant_id: int = Depends(get_current_tenant_id),
    *,
    request: Request,
) -> EraseUserResponse:
    """Plan de wissing van een medewerker van de EIGEN tenant (tenant uit de JWT)."""
    if user_id == int(current_user.id):
        raise HTTPException(status_code=409, detail="U kunt uw eigen gegevens niet zelf laten wissen")
    gebruiker = await _eigen_gebruiker(db, tenant_id, user_id)
    if gebruiker.email.endswith("@purged.invalid"):
        raise HTTPException(status_code=409, detail="De gegevens van deze gebruiker zijn al gewist")
    # Een platformbeheerder laat alleen wissen wie de platformrol zelf heeft (brief 2026-10-17).
    await eis_dat_gebruiker_uitgeschakeld_mag_worden(
        db, request, int(current_user.id), user_id, tenant_id
    )
    # Meten VOOR de wijziging: daarna is de gebruiker inactief en telt hij niet meer als beheerder.
    was_laatste_beheerder = await is_laatste_beheerder(db, tenant_id, user_id)

    gepland = plan_gebruiker_wissing(gebruiker, datetime.now(timezone.utc))
    await db.commit()

    await _schrijf_audit(
        db,
        tenant_id,
        int(current_user.id),
        "gdpr_user_erase_requested",
        f"user:{user_id}",
        {"scheduled_purge_date": gepland.isoformat()},
    )
    if was_laatste_beheerder:
        await meld_tenant_zonder_beheerder(tenant_id)

    return EraseUserResponse(
        user_id=user_id,
        status="gepland",
        scheduled_purge_date=gepland,
        message=(
            f"De gegevens van deze medewerker worden op {gepland.date().isoformat()} definitief "
            "gewist. Tot die datum kan deze persoon niet inloggen. U kunt dit tot die datum "
            "intrekken."
        ),
    )


@router.post(
    "/users/{user_id}/erase/revoke",
    response_model=RevokeResponse,
    summary="Trek de wissing van een medewerker in",
)
async def revoke_user_erase(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(require_user_manager_eigen_tenant),
    tenant_id: int = Depends(get_current_tenant_id),
) -> RevokeResponse:
    gebruiker = await _eigen_gebruiker(db, tenant_id, user_id)
    if gebruiker.deletion_scheduled_for is None:
        raise HTTPException(
            status_code=409, detail="Er is geen wissing gepland voor deze gebruiker"
        )
    if termijn_is_verstreken(gebruiker, datetime.now(timezone.utc)):
        raise HTTPException(status_code=409, detail=_TERMIJN_VERSTREKEN)
    trek_gebruiker_wissing_in(gebruiker)
    await db.commit()

    await _schrijf_audit(
        db, tenant_id, int(current_user.id), "gdpr_user_erase_revoked", f"user:{user_id}", {}
    )
    return RevokeResponse(status="ingetrokken", users_reactivated=1)


async def _zet_workflows_terug(db: AsyncSession, tenant_id: int, ids: list[str]) -> None:
    if not ids:
        return
    resultaat = await db.execute(
        select(Workflow).where(Workflow.tenant_id == tenant_id, Workflow.id.in_(ids))
    )
    for workflow in resultaat.scalars().all():
        workflow.is_active = True


@router.post(
    "/delete-all/revoke",
    response_model=RevokeResponse,
    summary="Trek een tenantbrede wissing in (binnen 30 dagen)",
)
async def revoke_delete_all(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
) -> RevokeResponse:
    if "admin" not in current_user.roles:
        raise HTTPException(status_code=403, detail="Intrekken vereist beheerdersrechten")

    lopend = await lopende_delete_all(db, tenant_id)
    if lopend is None:
        raise HTTPException(status_code=409, detail="Er is geen wissing gepland voor deze tenant")
    termijn, workflow_ids = lopend
    if termijn <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail=_TERMIJN_VERSTREKEN)

    alle = await gebruikers_met_geplande_wissing(db, tenant_id)
    groep = [g for g in alle if g.deletion_scheduled_for == termijn]
    if not groep:
        raise HTTPException(status_code=409, detail=_TERMIJN_VERSTREKEN)
    heractiveerd = 0
    for gebruiker in groep:
        werd_door_aanvraag_uitgezet = is_door_aanvraag_inactief(gebruiker)
        trek_gebruiker_wissing_in(gebruiker)
        heractiveerd += 1 if werd_door_aanvraag_uitgezet else 0
    await _zet_workflows_terug(db, tenant_id, workflow_ids)
    await db.commit()

    await _schrijf_audit(
        db,
        tenant_id,
        int(current_user.id),
        "gdpr_delete_all_revoked",
        f"tenant_data:{tenant_id}",
        {"users_reactivated": heractiveerd},
    )
    return RevokeResponse(status="ingetrokken", users_reactivated=heractiveerd)
