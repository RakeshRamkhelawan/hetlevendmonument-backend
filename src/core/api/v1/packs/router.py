"""Pakketten per klant aanzetten (pakket aanzetten, dag 1; ADR-033 Laag 1, ADR-039, ADR-005).

- `GET /api/v1/packs/activations` (`packs:execute`): de hele catalogus met per pakket aan of uit
  voor de EIGEN klant. Een pakket zonder rij staat uit.
- `PUT /api/v1/packs/activations/{pack_id}` (`packs:manage` + CSRF): een pakket aan- of uitzetten.
  Een `pack_id` buiten de catalogus geeft 404 `PACK_NOT_FOUND`; de klant komt uit de JWT, een
  `tenant_id` in de body wordt geweigerd. Elke wijziging krijgt een auditregel (`best_effort`).

De uitvoerroute (`POST /api/v1/agentic/packs/execute`) luistert naar deze stand: een pakket dat uit
staat geeft 403 `PACK_NOT_ENABLED`.

Importeert NOOIT direct database/governance/agents/workflow/llm: alleen `.dependencies` (Laag 2).
BEWUST GEEN `from __future__ import annotations`: de limiet-decorators gebruiken `functools.wraps`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from .dependencies import (
    PACK_ID_MAX_LENGTE,
    CataloguePack,
    PackActivationService,
    PakketStand,
    UserResponse,
    get_pack_activation_service,
    get_pack_catalogue,
    kan_pakketten_beheren,
    pack_activation_read_limit,
    pack_activation_write_limit,
    require_packs_execute,
    require_packs_manage,
    require_tenant_id,
    validate_csrf_token,
)
from .schemas import PackActivationRequest

router = APIRouter(prefix="/api/v1/packs", tags=["Packs"])


def _pack_niet_gevonden(pack_id: str) -> HTTPException:
    # Dezelfde vorm als `POST /api/v1/agentic/packs/execute`, zodat de frontend een code leest.
    return HTTPException(
        status_code=404,
        detail={
            "code": "PACK_NOT_FOUND",
            "message": f"Pack '{pack_id}' staat niet in de catalogus",
        },
    )


def _pakket(
    pack: CataloguePack, stand: PakketStand | None, *, met_wijziger: bool
) -> dict[str, object]:
    """Een pakket met zijn stand. Zonder rij (nooit aangeraakt) is het uit en onbekend door wie.

    `last_changed_by` (een e-mailadres) en `last_changed_at` staan alleen in het antwoord voor wie
    `packs:manage` heeft; een medewerker heeft het adres van de beheerder niet nodig
    (AVG-dataminimalisatie, besluit regie 2026-10-15). Voor een medewerker ontbreken de sleutels.
    """
    rij: dict[str, object] = {
        "pack_id": pack.pack_id,
        "name": pack.name,
        # Het scherm toont de Nederlandse weergavenaam; heeft een pakket er (nog) geen, dan de naam zelf.
        "display_name": pack.display_name or pack.name,
        "description": pack.description,
        "is_enabled": stand.is_enabled if stand else False,
    }
    if met_wijziger:
        rij["last_changed_by"] = stand.changed_by_email if stand else None
        rij["last_changed_at"] = stand.changed_at.isoformat() if stand else None
    return rij


@router.get("/activations")
@pack_activation_read_limit
async def list_pack_activations(
    request: Request,
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    service: PackActivationService = Depends(get_pack_activation_service),
    catalogue: dict[str, CataloguePack] = Depends(get_pack_catalogue),
    current_user: UserResponse = Depends(require_packs_execute),
    beheren: bool = Depends(kan_pakketten_beheren),
) -> dict[str, object]:
    """De hele catalogus met de stand van de eigen klant, op pakket-id gesorteerd."""
    standen = await service.stand_per_pakket(require_tenant_id())
    pakketten = sorted(catalogue.values(), key=lambda p: p.pack_id)
    return {
        "success": True,
        "data": [
            _pakket(p, standen.get(p.pack_id), met_wijziger=beheren)
            for p in pakketten[offset : offset + limit]
        ],
        "limit": limit,
        "offset": offset,
        "total": len(pakketten),
    }


@router.put("/activations/{pack_id}")
@pack_activation_write_limit
async def set_pack_activation(
    request: Request,
    pack_id: Annotated[str, Path(min_length=1, max_length=PACK_ID_MAX_LENGTE)],
    body: PackActivationRequest,
    service: PackActivationService = Depends(get_pack_activation_service),
    catalogue: dict[str, CataloguePack] = Depends(get_pack_catalogue),
    current_user: UserResponse = Depends(require_packs_manage),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Een pakket voor de eigen klant aan- of uitzetten; idempotent."""
    pack = catalogue.get(pack_id)
    if pack is None:
        raise _pack_niet_gevonden(pack_id)
    stand = await service.set_enabled(
        require_tenant_id(),
        pack_id,
        body.is_enabled,
        user_id=current_user.id,
        source_ip=request.client.host if request.client else "unknown",
        endpoint=str(request.url.path),
    )
    wijziging = PakketStand(
        is_enabled=stand.is_enabled,
        changed_by_email=current_user.email,
        changed_at=stand.enabled_at,
    )
    return {"success": True, "data": _pakket(pack, wijziging, met_wijziger=True)}
