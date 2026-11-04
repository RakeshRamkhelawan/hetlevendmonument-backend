"""Leveranciers vastleggen en lijsten: `POST` en `GET` onder `/api/v1/payables/suppliers` (crediteuren dag 1).

Zelfde prefix als `router.py`, eigen bestand: ADR-033 laat een routerbestand niet te groot worden. Zelfde regels: de tenant uit de
JWT-context, `payables:read` om te lezen, `payables:write` plus een CSRF-token om te schrijven.

BEWUST GEEN `from __future__ import annotations`: zie de moduledocstring van `router.py`.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.core.exceptions import ValidatieFout

from .dependencies import (
    NewSupplier,
    SupplierRepository,
    UserResponse,
    _resolve_tenant_id,
    consent_read_limit,
    consent_update_limit,
    get_current_user,
    get_supplier_repository,
    require_resource_permission,
    schrijf_crediteur_audit,
    validate_csrf_token,
)
from .schemas import SupplierCreate, SupplierOut

router = APIRouter(prefix="/suppliers", tags=["Crediteuren"])


def _uit(rij: object) -> dict[str, object]:
    return SupplierOut.model_validate(rij).model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED)
@consent_update_limit
async def create_supplier(
    request: Request,
    body: SupplierCreate,
    repo: SupplierRepository = Depends(get_supplier_repository),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("payables", "write")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Leg een leverancier van de eigen tenant vast."""
    tenant_id = _resolve_tenant_id(current_user)
    try:
        rij = await repo.add(
            tenant_id,
            NewSupplier(
                name=body.name, iban=body.iban, email=str(body.email) if body.email else None
            ),
        )
    except ValidatieFout as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Conflict.") from exc
    await repo.commit_and_refresh(rij)
    antwoord = _uit(rij)  # voor de auditregel: zie `create_payable` in router.py
    await schrijf_crediteur_audit(
        repo.db,
        event_type="supplier_created",
        user_id=user_id,
        tenant_id=tenant_id,
        pad=f"/api/v1/payables/suppliers/{antwoord['id']}",
        details={"supplier_id": antwoord["id"]},
    )
    return {"success": True, "data": antwoord}


@router.get("")
@consent_read_limit
async def list_suppliers(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repo: SupplierRepository = Depends(get_supplier_repository),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_resource_permission("payables", "read")),
) -> dict[str, object]:
    """De leveranciers van de eigen tenant, gepagineerd."""
    tenant_id = _resolve_tenant_id(current_user)
    rijen = await repo.list_for_tenant(tenant_id, limit=limit, offset=offset)
    return {"success": True, "data": [_uit(r) for r in rijen], "limit": limit, "offset": offset}
