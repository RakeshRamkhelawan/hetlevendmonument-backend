"""Inkoopfacturen vastleggen, lijsten en controleren: `POST`, `GET` en `PATCH` (crediteuren dag 1, Keten F).

ADR-033 Laag 1: dit bestand importeert geen database of governance; dat loopt via `.dependencies`. De tenant komt uit de JWT-context
(`_resolve_tenant_id`), nooit uit het verzoek. Lezen vraagt `payables:read` en mag 60 keer per minuut, schrijven vraagt
`payables:write` (rol `crediteuren` of `admin`), een CSRF-token en mag 10 keer per minuut (backend-patterns par. 4).

Dag 1 bouwt alleen het vastleggen en de stap naar `gecontroleerd`. Goedkeuren (dag 3), het betaalbestand en afboeken (dag 4) staan
er niet; de repository weigert die statussen met een Nederlandse tekst.

BEWUST GEEN `from __future__ import annotations`: de rate-limit-decorators gebruiken `functools.wraps`, en met uitgestelde
annotaties lost FastAPI het body-model niet meer op (422 op elke aanroep, gemeten 2026-08-06 in `tool_broker/hitl_router.py`).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.core.exceptions import ValidatieFout

from .dependencies import (
    NewPayable,
    PayableRepository,
    UserResponse,
    _resolve_tenant_id,
    consent_read_limit,
    consent_update_limit,
    get_current_user,
    get_payable_repository,
    require_resource_permission,
    schrijf_crediteur_audit,
    validate_csrf_token,
)
from .schemas import PayableCreate, PayableOut, PayableUpdate

router = APIRouter(prefix="/api/v1/payables", tags=["Crediteuren"])


def _uit(rij: object) -> dict[str, object]:
    """De factuur als antwoord, met de naam van de leverancier erbij (die laadt de repository mee)."""
    velden = PayableOut.model_validate(
        {
            "id": getattr(rij, "id"),
            "supplier_id": getattr(rij, "supplier_id"),
            "supplier_name": getattr(getattr(rij, "supplier"), "name"),
            "invoice_number": getattr(rij, "invoice_number"),
            "amount_cents": getattr(rij, "amount_cents"),
            "currency": getattr(rij, "currency"),
            "invoice_date": getattr(rij, "invoice_date"),
            "due_date": getattr(rij, "due_date"),
            "status": getattr(rij, "status"),
            "created_at": getattr(rij, "created_at"),
            "checked_at": getattr(rij, "checked_at"),
        }
    )
    return velden.model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED)
@consent_update_limit
async def create_payable(
    request: Request,
    body: PayableCreate,
    repo: PayableRepository = Depends(get_payable_repository),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
    # CSRF op de routes die STAAT WIJZIGEN, zelfde reden als in tool_broker/hitl_router.py (ADR-036 OP-72).
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Leg een inkoopfactuur van een leverancier van de eigen tenant vast."""
    tenant_id = _resolve_tenant_id(current_user)
    try:
        rij = await repo.add(
            tenant_id,
            NewPayable(
                supplier_id=body.supplier_id,
                invoice_number=body.invoice_number,
                amount_cents=body.amount_cents,
                currency=body.currency,
                invoice_date=body.invoice_date,
                due_date=body.due_date,
            ),
            created_by=user_id,
        )
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict.") from exc
    await repo.commit_and_refresh(rij)
    # Het antwoord VOOR de auditregel: `best_effort` draait bij een fout terug en laat het geladen object verlopen; het antwoord
    # kan daarna niet meer uit de rij worden opgebouwd (MissingGreenlet), terwijl de factuur WEL is vastgelegd (Gate 2).
    antwoord = _uit(rij)
    await schrijf_crediteur_audit(
        repo.db,
        event_type="payable_created",
        user_id=user_id,
        tenant_id=tenant_id,
        pad=f"/api/v1/payables/{antwoord['id']}",
        details={"payable_id": antwoord["id"], "invoice_number": antwoord["invoice_number"], "status": antwoord["status"]},
    )
    return {"success": True, "data": antwoord}


@router.get("")
@consent_read_limit
async def list_payables(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    repo: PayableRepository = Depends(get_payable_repository),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_resource_permission("payables", "read")),
) -> dict[str, object]:
    """De inkoopfacturen van de eigen tenant, gepagineerd en eventueel op status gefilterd."""
    tenant_id = _resolve_tenant_id(current_user)
    try:
        rijen = await repo.list_for_tenant(
            tenant_id, limit=limit, offset=offset, status=status_filter
        )
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return {"success": True, "data": [_uit(r) for r in rijen], "limit": limit, "offset": offset}


@router.patch("/{payable_id}")
@consent_update_limit
async def update_payable(
    request: Request,
    payable_id: int,
    body: PayableUpdate,
    repo: PayableRepository = Depends(get_payable_repository),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Zet de status van een inkoopfactuur van de eigen tenant. Een factuur van een ander bedrijf bestaat hier niet."""
    tenant_id = _resolve_tenant_id(current_user)
    bestaand = await repo.get(tenant_id, payable_id)
    if bestaand is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payable not found")
    oude_status = bestaand.status
    try:
        rij = await repo.set_status(tenant_id, payable_id, body.status, door=user_id)
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict.") from exc
    if rij is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payable not found")
    await repo.commit_and_refresh(rij)
    antwoord = _uit(rij)  # voor de auditregel, zie `create_payable`
    await schrijf_crediteur_audit(
        repo.db,
        event_type="payable_status_changed",
        user_id=user_id,
        tenant_id=tenant_id,
        pad=f"/api/v1/payables/{antwoord['id']}",
        details={"payable_id": antwoord["id"], "old_status": oude_status, "new_status": antwoord["status"]},
    )
    return {"success": True, "data": antwoord}
