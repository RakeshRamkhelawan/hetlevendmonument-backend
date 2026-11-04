"""Admin-endpoint waarmee een adviseur de LLM-providers van een tenant inricht.

ADR-036 B8: de inrichting is dienstverlening, geen zelfbediening. Er komt in deze ronde dus
GEEN klantscherm -- een adviseur zet dit bij de onboarding, en dat geeft meteen een auditspoor.

**Deze laag doet geen beleid EN geen wiring.** De twee sloten (mag deze tenant extern, en
deugt het adres) zitten in `TenantLLMProviderService`; het aan elkaar knopen van de onderdelen
gebeurt in `dependencies.py`. Dat laatste is geen smaak, en de bewakers noemden twee
verschillende redenen:

1. ADR-033 Contract 1 verbiedt een sub-router om domeinlogica rechtstreeks te importeren. De
   eerste versie van dit bestand deed dat wel (repository, service, security) --
   `test_importlinter_contract1_covers_sub_routers` en `test_dsm_api_violations` vielen om.
2. Ook NA die verplaatsing bleef `test_fan_out_budget[core_api]` rood, op 558 tegen een plafond
   van 557. Er was nog EEN paar over: dit bestand kende `src.core.auth` zelf, alleen om
   `UserResponse` als annotatie te gebruiken. Dat plafond is er om koppelingsgroei te stoppen,
   dus het antwoord is niet ophogen maar de import niet maken: `dependencies.py` her-exporteert
   `UserResponse` en kende `auth` toch al.

**De sleutel is write-only.** Hij gaat erin via het verzoek en komt er nooit uit; het
leesantwoord zegt alleen OF er een sleutel staat. Een beheerder die hem kwijt is, zet een
nieuwe -- dat is goedkoper dan een endpoint dat geheimen teruggeeft. Let op: die belofte hangt
er ook van af dat een sleutel niet via het ADRES naar binnen kan glippen
(`https://gebruiker:geheim@...` in een onversleutelde kolom). Dat wordt geweigerd in
`src/core/security/llm_endpoint_policy.py`, niet hier.

**`tenant_id` komt NOOIT uit de body** (CLAUDE.md, backend-patterns regel 1), maar uit de
geauthenticeerde gebruiker. Bewaakt door `test_geen_tenant_id_in_een_request_body.py`, en
sinds Gate 2 ook expliciet door `extra="forbid"` op het verzoekmodel: een meegestuurd
`tenant_id` wordt dan geweigerd in plaats van stilzwijgend genegeerd. Dat is dezelfde
verdediging die CVE-2026-59823 had voorkomen -- daar kwam een genest configuratieveld langs
de controle heen.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout

from .dependencies import (
    _current_user_value,
    _resolve_tenant_id,
    bouw_llm_provider_service,
    dubbele_volgorde_fout,
    get_db,
    is_dubbele_volgorde,
    llm_provider_fouten,
    require_admin_role,
    schrijf_llm_provider_audit,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


class ProviderInrichtingRequest(BaseModel):
    """Wat een adviseur opgeeft. Let op: GEEN tenant_id -- die komt uit het token."""

    # `extra="forbid"`: een onbekend veld is een fout en geen ruis. Zie de moduledocstring.
    model_config = ConfigDict(extra="forbid")

    volgorde: int = Field(ge=1, le=100, description="Plek in de failoverketen; lager gaat voor")
    naam: str = Field(min_length=1, max_length=64, description="Naam in logs en API-antwoord")
    base_url: str = Field(min_length=1, max_length=512, description="Moet https zijn")
    model: str = Field(min_length=1, max_length=128)
    # Write-only: dit veld staat met opzet NIET in het antwoordmodel.
    api_key: str | None = Field(default=None, max_length=512)
    actief: bool = True


@router.get("/llm-providers")
async def toon_llm_providers(
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    """De providerketen van deze tenant, ZONDER sleutels."""
    tenant_id = _resolve_tenant_id(current_user)
    _, geen_sleutel = llm_provider_fouten()
    try:
        service = bouw_llm_provider_service(db)
    except geen_sleutel as exc:
        raise _geen_hoofdsleutel(exc) from exc

    rijen = await service.toon(tenant_id)
    # In het geheugen pagineren en niet in de query: `volgorde` loopt tot 100, dus een tenant
    # heeft er hooguit honderd. Een LIMIT/OFFSET in de repository zou de tenantisolatietest
    # uitbreiden zonder dat er iets te beschermen valt. Backend-patterns regel 5 vraagt om de
    # parameters op elk list-endpoint; die zijn er, en ze doen wat ze beloven.
    venster = rijen[offset : offset + limit]
    return {
        "success": True,
        "data": [
            {
                "id": rij.id,
                "volgorde": rij.volgorde,
                "naam": rij.naam,
                "base_url": rij.base_url,
                "model": rij.model,
                "heeft_sleutel": rij.heeft_sleutel,
                "actief": rij.actief,
            }
            for rij in venster
        ],
        "meta": {"total": len(rijen), "limit": limit, "offset": offset},
    }


@router.post("/llm-providers", status_code=status.HTTP_201_CREATED)
async def richt_llm_provider_in(
    payload: ProviderInrichtingRequest,
    request: Request,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Voeg een provider toe aan de keten van deze tenant."""
    tenant_id = _resolve_tenant_id(current_user)
    beheerder_id = _current_user_value(current_user, "id")
    extern_verboden, geen_sleutel = llm_provider_fouten()
    ip = request.client.host if request.client else "unknown"

    try:
        service = bouw_llm_provider_service(db)
    except geen_sleutel as exc:
        raise _geen_hoofdsleutel(exc) from exc

    async def _audit(event_type: str, details: dict[str, object]) -> None:
        await schrijf_llm_provider_audit(
            db,
            event_type=event_type,
            user_id=beheerder_id,
            tenant_id=tenant_id,
            ip_address=ip,
            request_method="POST",
            details=details,
        )

    try:
        nieuw_id = await service.configureer(
            tenant_id,
            volgorde=payload.volgorde,
            naam=payload.naam,
            base_url=payload.base_url,
            model=payload.model,
            api_key=payload.api_key,
            actief=payload.actief,
        )
    except extern_verboden as exc:
        # Auditeren VOOR je weigert: een beheerder die interne adressen aftast hoort een spoor
        # achter te laten. Zelfde afweging als bij het aanmaken van beheerders (OP-184).
        await _audit(
            "LLM_PROVIDER_EXTERN_GEWEIGERD",
            {"reden": "externe_providers_niet_toegestaan", "naam": payload.naam},
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geen toegang.") from exc
    except ValidatieFout as exc:
        await _audit(
            "LLM_PROVIDER_ADRES_GEWEIGERD",
            {"reden": "ssrf_of_validatie", "naam": payload.naam},
        )
        # Een vaste Nederlandse tekst van de eigen dienst; de SSRF-reden staat in het log.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ValueError as exc:
        await _audit(
            "LLM_PROVIDER_ADRES_GEWEIGERD",
            {"reden": "ssrf_of_validatie", "naam": payload.naam},
        )
        # De reden mag naar de beheerder: hij moet zijn eigen typefout kunnen zien, en er is
        # nog geen netwerkaanroep gedaan waaruit iets zou kunnen lekken.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.") from exc
    except dubbele_volgorde_fout() as exc:
        if not is_dubbele_volgorde(exc):
            # Een andere integriteitsfout -- een verwijderde tenant, een NOT NULL, iets wat er
            # in fase 2b bijkomt. Die hoort de 500 te krijgen die erbij past: hem als 409
            # "volgorde al in gebruik" wegschrijven zou een defect als invoerfout vermommen.
            raise
        # 409 en niet 500: twee providers op dezelfde plek in de keten is een botsing die de
        # aanvrager zelf kan oplossen. Deze tak auditeert bewust NIET -- het is geen
        # beveiligingsgebeurtenis maar een invoerfout, en de sessie is na de IntegrityError
        # toch teruggedraaid.
        logger.warning(
            "provider niet toegevoegd voor tenant %s: volgorde %s is al bezet",
            tenant_id,
            payload.volgorde,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"volgorde {payload.volgorde} is voor deze tenant al in gebruik; "
                "kies een vrije plek in de keten"
            ),
        ) from exc

    # Primaire data EERST vastleggen (backend-patterns regel 3), en pas daarna het spoor.
    # `get_db` commit normaal gesproken na de handler, maar het auditblok hieronder draait
    # `best_effort` MET deze sessie: faalt het schrijven daar, dan doet die een rollback en
    # zou de zojuist aangemaakte providerrij verdwijnen terwijl hier al een id is
    # teruggegeven. Deze commit maakt die volgorde expliciet in plaats van impliciet.
    await db.commit()

    await _audit(
        "LLM_PROVIDER_INGERICHT",
        # GEEN sleutel en GEEN base_url met eventuele parameters: alleen wat nodig is om de
        # handeling terug te vinden.
        {"provider_id": nieuw_id, "naam": payload.naam, "volgorde": payload.volgorde},
    )
    return {"success": True, "data": {"id": nieuw_id}}


def _geen_hoofdsleutel(exc: Exception) -> HTTPException:
    """503 en niet 500: dit is een ontbrekende configuratie, geen defect."""
    logger.error("LLM-providerbeheer niet beschikbaar: %s", exc, exc_info=True)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Sleutelopslag is niet geconfigureerd. Zet MASTER_ENCRYPTION_KEY in de omgeving; "
            "zonder die sleutel worden opgeslagen klantsleutels onleesbaar na een herstart."
        ),
    )
