"""Bonnen uploaden en laten lezen (bonlezer dag 3, ADR-033 Laag 1).

- `POST /api/v1/bonnen` (`receipts:write`): een bon (pdf, jpg, png, tif) uploaden. De tenant komt uit de
  ingelogde gebruiker, nooit uit het verzoek. Grootte en soort worden gecontroleerd VOOR er iets op schijf
  komt. Het antwoord bevat het `bestand_id`; de bon zelf wordt door een aparte worker gelezen.
- `GET /api/v1/bonnen/{bestand_id}` (`receipts:read`): de stand. Een bon van een andere tenant is 404.

Importeert NOOIT direct database/governance/agents/workflow/llm -- alleen `.dependencies` (Laag 2).
"""

# BEWUST GEEN `from __future__ import annotations`: de limiet-decorator gebruikt `functools.wraps`
# (zie `v1/hr/deadlines_router.py`).

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool

from src.core.exceptions.exceptions import NotFoundError

from .dependencies import (
    MAX_BYTES,
    BonAudit,
    BonBevestiging,
    BonDienst,
    BonNietGevonden,
    UploadFout,
    UserResponse,
    _resolve_tenant_id,
    bonnen_read_limit,
    bonnen_upload_limit,
    bonnen_write_limit,
    get_bon_audit,
    get_bon_bevestiging,
    get_bon_dienst,
    require_receipts_read,
    require_receipts_write,
    validate_csrf_token,
)
from .btw_router import router as btw_router
from .schemas import BevestigingInvoer

router = APIRouter(prefix="/api/v1/bonnen", tags=["Bonnen"])


def _http(fout: UploadFout) -> HTTPException:
    # De boodschap als tekst: `error.message` van de standaardfoutvorm is dan leesbaar voor het scherm.
    return HTTPException(status_code=fout.status_code, detail=fout.boodschap)


@router.post("", status_code=201)
@bonnen_upload_limit
async def upload_bon(
    request: Request,
    file: UploadFile = File(...),
    audit: BonAudit = Depends(get_bon_audit),
    dienst: BonDienst = Depends(get_bon_dienst),
    current_user: UserResponse = Depends(require_receipts_write),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    # Een byte meer dan de grens: genoeg om "te groot" te zien zonder een onbegrensd bestand te lezen.
    inhoud = await file.read(MAX_BYTES + 1)
    try:
        bestand_id = await run_in_threadpool(
            dienst.uploaden, tenant_id, file.filename or "", inhoud
        )
    except UploadFout as fout:
        raise _http(fout) from fout
    await audit.upload(
        request,
        current_user,
        tenant_id=tenant_id,
        bestand_id=bestand_id,
        aantal_bytes=len(inhoud),
    )
    return {"success": True, "data": {"bestand_id": bestand_id, "status": "wachten"}}


@router.get("")
@bonnen_read_limit
async def lijst_bonnen(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    bevestiging: BonBevestiging = Depends(get_bon_bevestiging),
    dienst: BonDienst = Depends(get_bon_dienst),
    current_user: UserResponse = Depends(require_receipts_read),
) -> dict[str, object]:
    """De bonnen van de eigen tenant, nieuwste eerst (nooit uit een queryparameter).

    Een bon die niemand heeft geopend krijgt hier alsnog zijn leesresultaat (het wordt dan ook vastgelegd).
    """
    tenant_id = _resolve_tenant_id(current_user)

    def _ververs(bestand_id: str) -> None:
        dienst.status(tenant_id, bestand_id)

    items, totaal = await run_in_threadpool(
        lambda: bevestiging.lijst(tenant_id, limit=limit, offset=offset, ververs=_ververs)
    )
    return {"success": True, "data": {"items": items, "totaal": totaal}}


# De vaste padnaam MOET voor `/{bestand_id}` staan, anders wordt hij als een bon-id gelezen.
@router.get("/bevestigd.csv")
@bonnen_read_limit
async def exporteer_bevestigd(
    request: Request,
    bevestiging: BonBevestiging = Depends(get_bon_bevestiging),
    current_user: UserResponse = Depends(require_receipts_read),
) -> Response:
    tenant_id = _resolve_tenant_id(current_user)
    inhoud = await run_in_threadpool(bevestiging.csv_export, tenant_id)
    return Response(
        content=inhoud,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="bonnen-bevestigd.csv"'},
    )


# De routes van het btw-overzicht staan in een eigen sub-router (ADR-033: router.py max 200 regels). Hij hangt
# hier VOOR `/{bestand_id}`, anders wordt `btw-overzicht` als een bon-id gelezen.
router.include_router(btw_router)


@router.get("/{bestand_id}")
@bonnen_read_limit
async def bon_status(
    request: Request,
    bestand_id: str,
    dienst: BonDienst = Depends(get_bon_dienst),
    bevestiging: BonBevestiging = Depends(get_bon_bevestiging),
    current_user: UserResponse = Depends(require_receipts_read),
) -> dict[str, object]:
    tenant_id = _resolve_tenant_id(current_user)
    try:
        data = await run_in_threadpool(dienst.status, tenant_id, bestand_id)
    except BonNietGevonden as fout:
        raise NotFoundError("Bon") from fout
    except UploadFout as fout:
        raise _http(fout) from fout
    verrijkt = await run_in_threadpool(bevestiging.verrijk, tenant_id, bestand_id, data)
    return {"success": True, "data": verrijkt}


@router.put("/{bestand_id}/bevestiging")
@bonnen_write_limit
async def bevestig_bon(
    bestand_id: str,
    invoer: BevestigingInvoer,
    request: Request,
    audit: BonAudit = Depends(get_bon_audit),
    bevestiging: BonBevestiging = Depends(get_bon_bevestiging),
    current_user: UserResponse = Depends(require_receipts_write),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """De medewerker corrigeert de velden en bevestigt: alleen bevestigde velden gaan verder."""
    tenant_id = _resolve_tenant_id(current_user)
    try:
        record = await run_in_threadpool(
            bevestiging.bevestig,
            tenant_id,
            bestand_id,
            invoer.velden,
            gebruiker_id=int(current_user.id),
        )
    except BonNietGevonden as fout:
        raise NotFoundError("Bon") from fout
    except UploadFout as fout:
        raise _http(fout) from fout
    await audit.bevestigd(request, current_user, tenant_id=tenant_id, bestand_id=bestand_id)
    return {
        "success": True,
        "data": {"bestand_id": bestand_id, "bevestigd_op": record["bevestigd_op"]},
    }
