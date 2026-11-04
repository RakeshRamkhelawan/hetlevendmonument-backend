"""Het btw-overzicht per kwartaal (btw-overzicht, 2026-10-19; sub-router van `bonnen`, ADR-033).

- `GET /api/v1/bonnen/btw-overzicht?kwartaal=2026-Q3` (`receipts:read`): de voorbelasting (rubriek 5b) van het
  kwartaal uit de BEVESTIGDE bonnen van de eigen tenant. Zonder `kwartaal` het lopende kwartaal.
- `GET /api/v1/bonnen/btw-overzicht.csv?kwartaal=...`: dezelfde bonnen als CSV, met de totalen onderaan.

Een overzicht om zelf te controleren en over te nemen: geen omzetbelasting, geen indiening, geen advies. De tenant
komt uit de ingelogde gebruiker, nooit uit de query. Hij hangt in `router.py` VOOR `/{bestand_id}`.

Importeert NOOIT direct database/governance/agents/workflow/llm -- alleen `.dependencies` (Laag 2).
"""

# BEWUST GEEN `from __future__ import annotations`: de limiet-decorator gebruikt `functools.wraps`
# (zie `router.py`).

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool

from .dependencies import (
    BtwOverzicht,
    Kwartaal,
    UserResponse,
    _resolve_tenant_id,
    bonnen_read_limit,
    get_btw_overzicht,
    get_nu,
    huidig_kwartaal,
    parse_kwartaal,
    require_receipts_read,
)

router = APIRouter()


def _kwartaal(tekst: str | None, nu: datetime) -> Kwartaal:
    """Het gevraagde kwartaal (`2026-Q3`), zonder opgave het lopende; alles anders is een 422."""
    if tekst is None:
        return huidig_kwartaal(nu)
    gevonden = parse_kwartaal(tekst)
    if gevonden is None:
        raise HTTPException(
            status_code=422,
            detail="Dit kwartaal is niet geldig. Kies een kwartaal zoals 2026-Q3.",
        )
    return gevonden


@router.get("/btw-overzicht")
@bonnen_read_limit
async def btw_overzicht(
    request: Request,
    kwartaal: str | None = Query(default=None, max_length=16),
    nu: datetime = Depends(get_nu),
    overzicht: BtwOverzicht = Depends(get_btw_overzicht),
    current_user: UserResponse = Depends(require_receipts_read),
) -> dict[str, object]:
    """De voorbelasting (rubriek 5b) van een kwartaal uit de BEVESTIGDE bonnen van de eigen tenant."""
    tenant_id = _resolve_tenant_id(current_user)
    gevraagd = _kwartaal(kwartaal, nu)
    data = await run_in_threadpool(overzicht.overzicht, tenant_id, gevraagd)
    return {"success": True, "data": data}


@router.get("/btw-overzicht.csv")
@bonnen_read_limit
async def exporteer_btw_overzicht(
    request: Request,
    kwartaal: str | None = Query(default=None, max_length=16),
    nu: datetime = Depends(get_nu),
    overzicht: BtwOverzicht = Depends(get_btw_overzicht),
    current_user: UserResponse = Depends(require_receipts_read),
) -> Response:
    tenant_id = _resolve_tenant_id(current_user)
    gevraagd = _kwartaal(kwartaal, nu)
    inhoud = await run_in_threadpool(overzicht.csv_export, tenant_id, gevraagd)
    return Response(
        content=inhoud,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="btw-overzicht-{gevraagd.label()}.csv"'
        },
    )
