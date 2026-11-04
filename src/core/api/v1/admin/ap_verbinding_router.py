"""Beheerroute waarmee een PLATFORMBEHEERDER de ActivePieces-verbinding van een tenant vastlegt.

ADR-040 B3: waar de workflows van een bedrijf draaien en met welk account is inrichting door het
platform, geen zelfbediening. Daarom `require_platform_superuser` en niet `require_admin_role`:
een beheerder van een tenant mag dit voor zijn eigen bedrijf NIET veranderen.

**Het wachtwoord is write-only.** Het gaat erin via het verzoek en komt er nooit uit; het
leesantwoord zegt alleen OF er een wachtwoord staat. Een beheerder die hem kwijt is, zet een
nieuwe -- goedkoper dan een endpoint dat geheimen teruggeeft. Het wachtwoord staat ook nooit in de
auditregel of in een logregel.

**`tenant_id` staat in het PAD en nooit in de body.** Een platformbeheerder moet een andere
tenant kunnen aanwijzen, en een padparameter is niet wat CLAUDE.md verbiedt (body, payload,
query). `extra="forbid"` weigert bovendien een meegestuurd `tenant_id` in de body.

**Deze laag doet geen beleid EN geen wiring**: de adrescontrole en de versleuteling zitten in
`ApVerbindingBeheer`, het aan elkaar knopen in `dependencies.py` (ADR-033 Contract 1).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout

from .dependencies import (
    UserResponse,
    ap_hoofdsleutel_fout,
    bouw_ap_verbinding_beheer,
    get_db,
    require_platform_superuser,
    schrijf_ap_verbinding_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class ApVerbindingRequest(BaseModel):
    """Wat de platformbeheerder opgeeft. Let op: GEEN tenant_id -- die staat in het pad."""

    # `extra="forbid"`: een onbekend veld (ook `tenant_id`) is een fout en geen ruis.
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=1, max_length=512, description="https, of http naar localhost")
    email: str = Field(min_length=3, max_length=320, description="Het beheeraccount van de AP")
    # Write-only: dit veld staat met opzet NIET in het antwoord.
    wachtwoord: str = Field(min_length=1, max_length=512)
    project_id: str = Field(min_length=1, max_length=128)


def _antwoord(info: object) -> dict[str, object]:
    return {
        "tenant_id": getattr(info, "tenant_id"),
        "base_url": getattr(info, "base_url"),
        "email": getattr(info, "email"),
        "project_id": getattr(info, "project_id"),
        "heeft_wachtwoord": getattr(info, "heeft_wachtwoord"),
    }


def _geen_hoofdsleutel(exc: Exception) -> HTTPException:
    """503 en niet 500: dit is een ontbrekende configuratie, geen defect."""
    logger.error("AP-verbindingbeheer niet beschikbaar: %s", exc, exc_info=True)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Sleutelopslag is niet geconfigureerd. Zet MASTER_ENCRYPTION_KEY in de omgeving; "
            "zonder die sleutel wordt een opgeslagen wachtwoord onleesbaar na een herstart."
        ),
    )


@router.get("/tenants/{tenant_id}/ap-verbinding")
async def toon_ap_verbinding(
    tenant_id: int,
    _beheerder: UserResponse = Depends(require_platform_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """De verbinding van deze tenant, ZONDER wachtwoord."""
    geen_sleutel = ap_hoofdsleutel_fout()
    try:
        beheer = bouw_ap_verbinding_beheer(db)
    except geen_sleutel as exc:
        raise _geen_hoofdsleutel(exc) from exc

    info = await beheer.toon(tenant_id)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Geen verbinding ingesteld"
        )
    return {"success": True, "data": _antwoord(info)}


@router.put("/tenants/{tenant_id}/ap-verbinding")
async def leg_ap_verbinding_vast(
    tenant_id: int,
    payload: ApVerbindingRequest,
    request: Request,
    beheerder: UserResponse = Depends(require_platform_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Leg de verbinding van deze tenant vast of werk hem bij."""
    geen_sleutel = ap_hoofdsleutel_fout()
    ip = request.client.host if request.client else "unknown"
    beheerder_id = getattr(beheerder, "id", None)

    try:
        beheer = bouw_ap_verbinding_beheer(db)
    except geen_sleutel as exc:
        raise _geen_hoofdsleutel(exc) from exc

    try:
        info = await beheer.leg_vast(
            tenant_id,
            base_url=payload.base_url,
            email=payload.email,
            wachtwoord=payload.wachtwoord,
            project_id=payload.project_id,
        )
        await db.flush()
    except ValidatieFout as exc:
        await schrijf_ap_verbinding_audit(
            db,
            event_type="AP_VERBINDING_GEWEIGERD",
            user_id=beheerder_id,
            tenant_id=tenant_id,
            ip_address=ip,
            request_method="PUT",
            details={"reden": "gegevens_niet_toegestaan"},
        )
        # De reden mag naar de beheerder (zijn eigen typefout); er is geen netwerkaanroep gedaan.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntegrityError as exc:
        await db.rollback()
        if "uq_tenant_ap_verbindingen_adres_project" in str(exc.orig):
            # 409 ZONDER te zeggen welke tenant het project al heeft: dat is een ander bedrijf.
            await schrijf_ap_verbinding_audit(
                db,
                event_type="AP_VERBINDING_GEWEIGERD",
                user_id=beheerder_id,
                tenant_id=tenant_id,
                ip_address=ip,
                request_method="PUT",
                details={"reden": "adres_en_project_al_in_gebruik"},
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Dit adres met dit project is al in gebruik door een andere verbinding.",
            ) from exc
        melding = str(exc.orig)
        if "uq_tenant_ap_verbindingen_tenant" in melding:
            await schrijf_ap_verbinding_audit(
                db,
                event_type="AP_VERBINDING_GEWEIGERD",
                user_id=beheerder_id,
                tenant_id=tenant_id,
                ip_address=ip,
                request_method="PUT",
                details={"reden": "gelijktijdige_wijziging"},
            )
            # Een gelijktijdige tweede PUT voor dezelfde tenant: opnieuw proberen lukt wel.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Er wordt al een verbinding voor deze tenant vastgelegd; probeer opnieuw.",
            ) from exc
        if "tenant_id_fkey" in melding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Deze tenant bestaat niet"
            ) from exc
        # Elke andere integriteitsfout is een defect en geen invoerfout: niet vermommen.
        raise

    # Primaire data EERST vastleggen (backend-patterns regel 3), dan pas het spoor.
    await db.commit()
    await schrijf_ap_verbinding_audit(
        db,
        event_type="AP_VERBINDING_VASTGELEGD",
        user_id=beheerder_id,
        tenant_id=tenant_id,
        ip_address=ip,
        request_method="PUT",
        # GEEN wachtwoord, en geen adres met eventuele parameters: alleen wat nodig is om de
        # handeling terug te vinden.
        details={"project_id": getattr(info, "project_id", None)},
    )
    return {"success": True, "data": _antwoord(info)}
