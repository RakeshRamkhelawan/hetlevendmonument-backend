"""Een inkoopfactuur inlezen: uploaden, het voorstel zien en bevestigen (crediteuren dag 2, Keten F).

- `POST /api/v1/payables/inlezen`: een factuur (pdf, jpg, png, tif) uploaden. Grootte en soort worden gecontroleerd voor er iets op schijf
  komt; een aparte worker zonder netwerk leest hem (de bonlezer, hergebruikt). Het antwoord bevat het `bestand_id`.
- `GET /api/v1/payables/inlezen/{bestand_id}`: de stand van het lezen en, als hij gelezen is, de gelezen velden en het voorstel voor
  de leverancier (met een waarschuwing bij een afwijkend IBAN). Er wordt niets vastgelegd.
- `POST /api/v1/payables/inlezen/{bestand_id}/bevestiging`: de medewerker bevestigt de (aangepaste) velden; DAN ontstaat de
  inkoopfactuur met status `ontvangen`. Een upload wordt hooguit een keer een factuur.

Alles vraagt `payables:write`; de tenant komt uit de JWT-context. Geen mail-inlezen (komt later) en geen goedkeuren (dag 3).

ADR-033 Laag 1: dit bestand importeert geen database of governance, alleen `.inlezen_dependencies` en `.dependencies`.
BEWUST GEEN `from __future__ import annotations`: zie de moduledocstring van `router.py`.
"""

from collections.abc import Callable

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from starlette.concurrency import run_in_threadpool

from src.core.exceptions import ValidatieFout

from .dependencies import (
    UserResponse,
    _resolve_tenant_id,
    consent_update_limit,
    get_current_user,
    require_resource_permission,
    schrijf_crediteur_audit,
    validate_csrf_token,
)
from .inlezen_dependencies import (
    MAX_BYTES,
    Bevestiging,
    BonDienst,
    InkoopfactuurInlezen,
    InlezenFout,
    NewSupplier,
    UploadFout,
    bonnen_read_limit,
    bonnen_upload_limit,
    get_bon_dienst,
    get_inlezen_dienst,
    get_verwerking_starter,
    vereis_goedkeurrecht,
    weiger_zelfgoedkeuring,
)
from .inlezen_schemas import InlezenBevestiging
from .router import _uit

router = APIRouter(prefix="/inlezen", tags=["Crediteuren"])


def _http(fout: InlezenFout) -> HTTPException:
    return HTTPException(status_code=fout.status_code, detail=fout.boodschap)


@router.post("", status_code=status.HTTP_201_CREATED)
@bonnen_upload_limit
async def upload_inkoopfactuur(
    request: Request,
    file: UploadFile = File(...),
    inlezen: InkoopfactuurInlezen = Depends(get_inlezen_dienst),
    dienst: BonDienst = Depends(get_bon_dienst),
    start: Callable[[int, str, int], None] = Depends(get_verwerking_starter),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Bewaar de factuur van de eigen tenant en laat hem lezen; de crediteurenagent verwerkt hem daarna zelf."""
    tenant_id = _resolve_tenant_id(current_user)
    # Een byte meer dan de grens: genoeg om "te groot" te zien zonder een onbegrensd bestand te lezen.
    inhoud = await file.read(MAX_BYTES + 1)
    try:
        bestand_id = await run_in_threadpool(
            dienst.uploaden, tenant_id, file.filename or "", inhoud, "factuur"
        )
    except UploadFout as fout:
        raise HTTPException(status_code=fout.status_code, detail=fout.boodschap) from fout
    await schrijf_crediteur_audit(
        inlezen.db,
        event_type="payable_upload",
        user_id=user_id,
        tenant_id=tenant_id,
        pad="/api/v1/payables/inlezen",
        # Alleen een nummer en een aantal: geen bestandsnaam en geen inhoud in de auditregel.
        details={"bestand_id": bestand_id, "bytes": len(inhoud)},
    )
    # De agent wacht in de achtergrond tot de bonlezer klaar is; de verantwoordelijke gebruiker is degene die uploadde.
    start(tenant_id, bestand_id, user_id)
    return {"success": True, "data": {"bestand_id": bestand_id, "status": "wachten"}}


@router.get("/{bestand_id}")
@bonnen_read_limit
async def inlezen_status(
    request: Request,
    bestand_id: str,
    inlezen: InkoopfactuurInlezen = Depends(get_inlezen_dienst),
    start: Callable[[int, str, int], None] = Depends(get_verwerking_starter),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
) -> dict[str, object]:
    """De stand van het lezen, het voorstel en wat de agent ermee deed. Een factuur van een andere tenant is 404.

    Is de factuur gelezen en heeft de agent hem nog niet verwerkt (bijvoorbeeld door een herstart van de API), dan start dit de
    verwerking alsnog; een claim naast de upload zorgt dat een tweede start niets dubbel doet.
    """
    tenant_id = _resolve_tenant_id(current_user)
    try:
        data = await inlezen.voorstel(tenant_id, bestand_id)
    except InlezenFout as fout:
        raise _http(fout) from fout
    except UploadFout as fout:
        raise HTTPException(status_code=fout.status_code, detail=fout.boodschap) from fout
    if data.get("status") == "gelezen" and data.get("verwerking") is None:
        start(tenant_id, bestand_id, user_id)
    return {"success": True, "data": data}


@router.post("/{bestand_id}/bevestiging", status_code=status.HTTP_201_CREATED)
@consent_update_limit
async def bevestig_inkoopfactuur(
    request: Request,
    bestand_id: str,
    body: InlezenBevestiging,
    inlezen: InkoopfactuurInlezen = Depends(get_inlezen_dienst),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Leg de inkoopfactuur vast die de medewerker na controle bevestigt."""
    tenant_id = _resolve_tenant_id(current_user)
    await vereis_goedkeurrecht(inlezen.db, current_user)
    try:
        ticket = await inlezen.ticket(tenant_id, body.ticket_ref)
    except InlezenFout as fout:
        raise _http(fout) from fout
    await weiger_zelfgoedkeuring(inlezen.db, request, current_user, ticket)
    invoer = Bevestiging(
        invoice_number=body.invoice_number,
        amount_cents=body.amount_cents,
        currency=body.currency,
        invoice_date=body.invoice_date,
        due_date=body.due_date,
        supplier_id=body.supplier_id,
        nieuwe_leverancier=(
            NewSupplier(
                name=body.nieuwe_leverancier.name,
                iban=body.nieuwe_leverancier.iban,
                email=body.nieuwe_leverancier.email,
            )
            if body.nieuwe_leverancier is not None
            else None
        ),
        iban=body.iban,
        iban_afwijking_bevestigd=body.iban_afwijking_bevestigd,
        ticket_ref=body.ticket_ref,
        reden=body.reden,
    )
    try:
        vastgelegd = await inlezen.bevestig(tenant_id, bestand_id, invoer, user_id=user_id)
    except InlezenFout as fout:
        raise _http(fout) from fout
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict.") from exc
    # Het antwoord VOOR de auditregel, zoals bij `create_payable`: `best_effort` kan het object laten verlopen.
    antwoord = _uit(vastgelegd.payable)
    await schrijf_crediteur_audit(
        inlezen.db,
        event_type="payable_created",
        user_id=user_id,
        tenant_id=tenant_id,
        pad=f"/api/v1/payables/{antwoord['id']}",
        # Geen IBAN en geen bedrag: wel of het via inlezen kwam, of de leverancier nieuw was en of een afwijkend IBAN
        # uitdrukkelijk is bevestigd.
        details={
            "payable_id": antwoord["id"],
            "invoice_number": antwoord["invoice_number"],
            "status": antwoord["status"],
            "bestand_id": bestand_id,
            "via": "inlezen_aanpassen",
            "ticket_ref": body.ticket_ref,
            "leverancier_nieuw": vastgelegd.leverancier_nieuw,
            "iban_afwijking_bevestigd": vastgelegd.iban_afwijking_bevestigd,
        },
    )
    return {"success": True, "data": antwoord}
