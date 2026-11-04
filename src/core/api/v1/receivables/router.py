"""Handmatige invoer van debiteuren: `POST`, `GET` (lijst) en `PATCH` (debiteurenagent dag 2).

Besluit Rakesh (dag 1): debiteuren komen eerst met de hand binnen; import en een koppeling met
een boekhoudpakket volgen later. Deze drie routes zijn dat begin.

ADR-033 Laag 1: dit bestand importeert geen database of governance; dat loopt via
`.dependencies`. De tenant komt uit de JWT-context (`_resolve_tenant_id`), nooit uit het verzoek.
Lezen vraagt `receivables:read` en mag 60 keer per minuut, schrijven vraagt
`receivables:write` (rol `debiteuren` of `admin`, rolmodel optie A), een CSRF-token en mag 10 keer per minuut (backend-patterns par. 4).

BEWUST GEEN `from __future__ import annotations`: de rate-limit-decorators gebruiken
`functools.wraps`, en met uitgestelde annotaties lost FastAPI het body-model niet meer op (422 op
elke aanroep, gemeten 2026-08-06 in `tool_broker/hitl_router.py`).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.core.exceptions import ValidatieFout

from .dependencies import (
    NewReceivable,
    ReceivableChanges,
    ReceivableRepository,
    UserResponse,
    _resolve_tenant_id,
    consent_read_limit,
    consent_update_limit,
    get_current_user,
    get_receivable_repository,
    require_resource_permission,
    schrijf_debiteur_audit,
    scheid_bestaande_voorstellen,
    schrijf_voorstel_audit,
    start_reminder_proposals,
    voeg_uitkomsten_samen,
    validate_csrf_token,
)
from .schemas import ReceivableCreate, ReceivableOut, ReceivableUpdate, ReminderProposalRequest

router = APIRouter(prefix="/api/v1/receivables", tags=["Debiteuren"])


def _uit(rij: object) -> dict[str, object]:
    return ReceivableOut.model_validate(rij).model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED)
@consent_update_limit
async def create_receivable(
    request: Request,
    body: ReceivableCreate,
    repo: ReceivableRepository = Depends(get_receivable_repository),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("receivables", "write")),
    # CSRF op de routes die STAAT WIJZIGEN, zelfde reden als in tool_broker/hitl_router.py
    # (ADR-036 OP-72): get_current_user accepteert ook het access_token-cookie.
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Voer een openstaande factuur met de hand in."""
    tenant_id = _resolve_tenant_id(current_user)
    rij = await repo.add(
        tenant_id,
        NewReceivable(
            customer_name=body.customer_name,
            customer_email=str(body.customer_email),
            invoice_number=body.invoice_number,
            amount=body.amount,
            currency=body.currency,
            due_date=body.due_date,
        ),
    )
    await repo.commit_and_refresh(rij)
    await schrijf_debiteur_audit(
        repo,
        event_type="receivable_created",
        user_id=user_id,
        tenant_id=tenant_id,
        receivable_id=rij.id,
        details={"invoice_number": rij.invoice_number, "status": rij.status},
    )
    return {"success": True, "data": _uit(rij)}


@router.get("")
@consent_read_limit
async def list_receivables(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: ReceivableRepository = Depends(get_receivable_repository),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_resource_permission("receivables", "read")),
) -> dict[str, object]:
    """De debiteuren van de eigen tenant, gepagineerd."""
    tenant_id = _resolve_tenant_id(current_user)
    rijen = await repo.list_for_tenant(tenant_id, limit=limit, offset=offset)
    return {
        "success": True,
        "data": [_uit(r) for r in rijen],
        "limit": limit,
        "offset": offset,
    }


@router.patch("/{receivable_id}")
@consent_update_limit
async def update_receivable(
    request: Request,
    receivable_id: int,
    body: ReceivableUpdate,
    repo: ReceivableRepository = Depends(get_receivable_repository),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("receivables", "write")),
    # CSRF op de routes die STAAT WIJZIGEN, zelfde reden als in tool_broker/hitl_router.py
    # (ADR-036 OP-72): get_current_user accepteert ook het access_token-cookie.
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Wijzig een debiteur van de eigen tenant. Een factuur van een ander bedrijf bestaat hier niet."""
    tenant_id = _resolve_tenant_id(current_user)
    velden = body.model_dump(exclude_none=True)
    if "customer_email" in velden:
        velden["customer_email"] = str(velden["customer_email"])
    bestaand = await repo.get(tenant_id, receivable_id)
    if bestaand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receivable not found")
    oude_status = bestaand.status
    try:
        rij = await repo.update(tenant_id, receivable_id, ReceivableChanges(**velden))
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict.") from exc
    if rij is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receivable not found")
    await repo.commit_and_refresh(rij)
    if rij.status != oude_status:
        await schrijf_debiteur_audit(
            repo,
            event_type="receivable_status_changed",
            user_id=user_id,
            tenant_id=tenant_id,
            receivable_id=rij.id,
            details={
                "old_status": oude_status,
                "new_status": rij.status,
                "reden": velden.get("reden"),
            },
        )
    return {"success": True, "data": _uit(rij)}


@router.post("/reminder-proposals")
@consent_update_limit
async def propose_reminders(
    request: Request,
    body: ReminderProposalRequest,
    repo: ReceivableRepository = Depends(get_receivable_repository),
    current_user: UserResponse = Depends(get_current_user),
    # Hetzelfde smalle recht als de agent-tool `send_payment_reminder` (`receivables:propose`).
    # `write` was breder: daarmee zet je ook een factuur op `betaald`.
    user_id: int = Depends(require_resource_permission("receivables", "propose")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Start de debiteurenagent: per factuur een brief klaarzetten die op goedkeuring wacht.

    Wie op de knop drukt, is de aanvrager in het ticket. Er gaat hier niets de deur uit: elke
    brief wacht op een mens (`/hitl`).
    """
    tenant_id = _resolve_tenant_id(current_user)
    # Geen tweede voorstel voor een factuur waarvoor er al een op een besluit wacht.
    nieuwe, geweigerd = await scheid_bestaande_voorstellen(
        repo.db, tenant_id=tenant_id, receivable_ids=body.receivable_ids
    )
    gestart = (
        await start_reminder_proposals(
            tenant_id=tenant_id, user_id=user_id, receivable_ids=nieuwe, kind=body.kind
        )
        if nieuwe
        else []
    )
    uitkomsten = voeg_uitkomsten_samen(body.receivable_ids, geweigerd, gestart)
    await schrijf_voorstel_audit(
        repo, tenant_id=tenant_id, user_id=user_id, kind=body.kind, uitkomsten=uitkomsten
    )
    return {"success": True, "data": uitkomsten}
