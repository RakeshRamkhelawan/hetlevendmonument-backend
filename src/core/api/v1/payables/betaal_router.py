"""Het betaalvoorstel en het betaalbestand (crediteuren dag 3, Keten F).

- `GET /api/v1/payables/betaalvoorstel`: wat de crediteurenagent NU zou voorstellen (facturen die binnen 7 dagen vervallen of al te laat
  zijn), met de reden per regel. Er wordt niets vastgelegd.
- `POST /api/v1/payables/betaalvoorstel`: de agent legt EEN voorstel voor aan een mens (een ticket in de goedkeurwachtrij). De agent
  betaalt niets en keurt niets goed. Boven het drempelbedrag per factuur geldt vier ogen: wie dit aanroept mag het voorstel niet zelf
  goedkeuren.
- `POST /api/v1/payables/betaalbestand`: wie het goedkeurrecht heeft haalt het SEPA-betaalbestand (pain.001.001.09) op van ALLE
  goedgekeurde facturen, als tekst in het antwoord (de browser maakt er de download van). Dat kan een keer per factuur: daarna staan ze
  op `in_betaalbestand`. Het bestand gaat nergens heen.

`GET` en het voorstel vragen `payables:write`; het bestand vraagt `payables:approve`. De tenant komt uit de JWT-context.

ADR-033 Laag 1: dit bestand importeert geen database of governance, alleen `.betaal_dependencies` en `.dependencies`.
BEWUST GEEN `from __future__ import annotations`: zie de moduledocstring van `router.py`.
"""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidatieFout

from .betaal_dependencies import (
    BetaalrunRegistry,
    get_betaalrun_registry,
    get_voorstel_starter,
    vereis_goedkeurrecht,
)
from .betaal_schemas import BetaalbestandAanvraag, IntrekkenAanvraag, VoorstelIntrekkenAanvraag
from .dependencies import (
    UserResponse,
    _resolve_tenant_id,
    consent_read_limit,
    consent_update_limit,
    get_current_user,
    get_db,
    require_resource_permission,
    validate_csrf_token,
)

router = APIRouter(tags=["Crediteuren"])

#: Wat de klant van een regel in het voorstel te zien krijgt: geen interne sleutels en geen digest.
_ZICHTBAAR = ("supplier_name", "invoice_number", "amount_cents", "due_date", "iban", "waarom")


@router.get("/betaalvoorstel")
@consent_read_limit
async def betaalvoorstel_bekijken(
    request: Request,
    registry: BetaalrunRegistry = Depends(get_betaalrun_registry),
    current_user: UserResponse = Depends(get_current_user),
    _recht: int = Depends(require_resource_permission("payables", "write")),
) -> dict[str, object]:
    """Wat de agent nu zou voorstellen. Legt niets vast en maakt geen ticket."""
    tenant_id = _resolve_tenant_id(current_user)
    selectie = await registry.selecteer(tenant_id)
    regels = selectie["regels"] if isinstance(selectie["regels"], list) else []
    return {
        "success": True,
        "data": {
            "regels": [{k: r[k] for k in _ZICHTBAAR} for r in regels if isinstance(r, dict)],
            "overgeslagen": selectie["overgeslagen"],
            "totaal_cents": selectie["totaal_cents"],
            "drempel_cents": selectie["drempel_cents"],
            "vier_ogen_vereist": selectie["vier_ogen_vereist"],
        },
    }


@router.post("/betaalvoorstel")
@consent_update_limit
async def betaalvoorstel_maken(
    request: Request,
    response: Response,
    start: Callable[[int, int], Awaitable[dict[str, object]]] = Depends(get_voorstel_starter),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """De crediteurenagent legt een betaalvoorstel voor aan een mens. De aanroeper is de verantwoordelijke voor het voorstel."""
    tenant_id = _resolve_tenant_id(current_user)
    uitkomst = await start(tenant_id, user_id)
    if uitkomst.get("uitkomst") in ("niet_gelukt", "geweigerd"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(uitkomst.get("reden") or "Het betaalvoorstel kon niet worden gemaakt."),
        )
    if uitkomst.get("uitkomst") == "ticket":
        response.status_code = status.HTTP_201_CREATED
    return {"success": True, "data": uitkomst}


@router.post("/betaalvoorstel/intrekken")
@consent_update_limit
async def betaalvoorstel_intrekken(
    request: Request,
    body: VoorstelIntrekkenAanvraag,
    db: AsyncSession = Depends(get_db),
    registry: BetaalrunRegistry = Depends(get_betaalrun_registry),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "read")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Trek een goedgekeurd betaalvoorstel in zolang het betaalbestand nog niet is gemaakt; de facturen komen vrij voor een nieuw voorstel.

    Alleen met het goedkeurrecht (`payables:approve`, procesbevoegdheid; geen beheerdersrol) en met een reden van minstens tien tekens;
    elk intrekken komt in het auditlog. Na het maken van het bestand kan het niet meer (het bestand is eenmalig).
    """
    tenant_id = _resolve_tenant_id(current_user)
    await vereis_goedkeurrecht(db, current_user)
    try:
        uitkomst = await registry.trek_voorstel_in(
            tenant_id, ticket_ref=body.ticket_ref, door=user_id, reden=body.reden
        )
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if uitkomst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return {"success": True, "data": uitkomst}


@router.post("/{payable_id}/intrekken")
@consent_update_limit
async def factuur_intrekken(
    request: Request,
    payable_id: int,
    body: IntrekkenAanvraag,
    db: AsyncSession = Depends(get_db),
    registry: BetaalrunRegistry = Depends(get_betaalrun_registry),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "read")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Trek een goedgekeurde factuur in (status `afgewezen`) zolang hij in geen betaalbestand zit.

    Alleen met het goedkeurrecht (`payables:approve`) en met een reden van minstens tien tekens in het auditlog. Een factuur van een ander
    bedrijf bestaat hier niet (404).
    """
    tenant_id = _resolve_tenant_id(current_user)
    await vereis_goedkeurrecht(db, current_user)
    try:
        uitkomst = await registry.trek_factuur_in(
            tenant_id, payable_id, door=user_id, reden=body.reden
        )
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if uitkomst is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payable not found")
    return {"success": True, "data": uitkomst}


@router.post("/betaalbestand")
@consent_update_limit
async def betaalbestand_ophalen(
    request: Request,
    response: Response,
    body: BetaalbestandAanvraag,
    db: AsyncSession = Depends(get_db),
    registry: BetaalrunRegistry = Depends(get_betaalrun_registry),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "read")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Het SEPA-betaalbestand van alle goedgekeurde facturen; eenmalig per factuur (daarna `in_betaalbestand`).

    Het bestand staat als TEKST in het antwoord (`bestand`, UTF-8 XML) en de browser maakt er de download van: de gedeelde API-client
    leest elk antwoord als JSON. De bestandsnaam staat in `bestandsnaam`.
    """
    tenant_id = _resolve_tenant_id(current_user)
    await vereis_goedkeurrecht(db, current_user)
    try:
        bestand, meta = await registry.maak_betaalbestand(
            tenant_id,
            door=user_id,
            debiteur_naam=body.debiteur_naam,
            debiteur_iban=body.debiteur_iban,
            uitvoerdatum=body.uitvoerdatum,
        )
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    # Een bankbestand hoort niet in een cache van de browser of een tussenserver.
    response.headers["Cache-Control"] = "no-store"
    return {
        "success": True,
        "data": {
            "bestand": bestand.decode("utf-8"),
            "bestandsnaam": f"betaalbestand-{meta['bericht_id']}.xml",
            "aantal": meta["aantal"],
            "totaal_cents": meta["totaal_cents"],
            "bericht_id": meta["bericht_id"],
            # Facturen die NIET in dit bestand zitten (de leverancier is na de goedkeuring gewijzigd); ze blijven goedgekeurd.
            "overgeslagen": meta["overgeslagen"],
        },
    }
