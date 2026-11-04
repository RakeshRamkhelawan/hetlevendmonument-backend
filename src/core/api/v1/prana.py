"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
Prana Economy REST API.

Exposes the in-memory prana ledger for all agents of the active tenant.
No database access; all data comes from the per-tenant ContractManager.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db, require_authenticated_user
from src.core.api.v1._prana_contracts_cache import get_contract_manager
from src.core.auth.scope_validator import require_scopes
from src.core.auth.scopes import OAuth2Scope
from src.core.middleware.tenant_context import require_tenant_id, safe_get_tenant_id

router = APIRouter(prefix="/prana", tags=["Prana"])


class PranaBalanceEntry(BaseModel):
    agent_id: str
    balance: int


class PranaBalanceResponse(BaseModel):
    tenant_id: int
    balances: list[PranaBalanceEntry]
    total_agents: int


class PranaLedgerEntry(BaseModel):
    agent_id: str
    balance: int
    last_updated: str


class PranaLedgerResponse(BaseModel):
    tenant_id: int
    entries: list[PranaLedgerEntry]
    total: int
    limit: int
    offset: int


@router.get("/balance", response_model=PranaBalanceResponse)
async def get_prana_balance(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tenant_id: int = Depends(safe_get_tenant_id),
    _user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> PranaBalanceResponse:
    """Get prana balances for all agents of the active tenant."""
    manager = get_contract_manager(tenant_id)
    # Access internal ledger aEUR" public accessor methods do not yet exist on ContractManager
    all_entries = [
        PranaBalanceEntry(agent_id=aid, balance=bal) for aid, bal in manager._prana_ledger.items()
    ]
    paginated = all_entries[offset : offset + limit]
    return PranaBalanceResponse(
        tenant_id=tenant_id,
        balances=paginated,
        total_agents=len(all_entries),
    )


@router.get("/ledger", response_model=PranaLedgerResponse)
async def get_prana_ledger(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tenant_id: int = Depends(safe_get_tenant_id),
    _user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_authenticated_user
    ),
) -> PranaLedgerResponse:
    """Get paginated prana ledger entries for all agents of the active tenant."""
    manager = get_contract_manager(tenant_id)
    now_iso = datetime.now(timezone.utc).isoformat()
    all_entries = [
        PranaLedgerEntry(agent_id=aid, balance=bal, last_updated=now_iso)
        for aid, bal in manager._prana_ledger.items()
    ]
    paginated = all_entries[offset : offset + limit]
    return PranaLedgerResponse(
        tenant_id=tenant_id,
        entries=paginated,
        total=len(all_entries),
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# ADR-021 department prana economy (DB-backed) -- separate from the A2A ledger above.
# ---------------------------------------------------------------------------


class PranaDepartmentBudgetEntry(BaseModel):
    department: str
    total_prana: int
    spent_prana: int
    available: int


class PranaBudgetsResponse(BaseModel):
    tenant_id: int
    budgets: list[PranaDepartmentBudgetEntry]


class EmergencyAllocationRequest(BaseModel):
    department: str
    amount: int = Field(gt=0, description="Prana to add to the department budget")
    reason: str = Field(min_length=1, max_length=500)


class EmergencyAllocationResponse(BaseModel):
    success: bool
    department: str
    amount: int
    balance_after: int


@router.get("/budgets", response_model=PranaBudgetsResponse)
async def get_prana_budgets(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    _user_id: int = Depends(require_scopes(OAuth2Scope.PRANA_READ)),
) -> PranaBudgetsResponse:
    """Department prana budgets for the active tenant (ADR-021, DB-backed)."""
    # Dynamisch via importlib (i.p.v. `from ... import`) om deze API-laag niet direct aan
    # governance te koppelen (ADR-033) -- zie test_dsm002_dag6_zero_violations.py.
    import importlib

    prana_service_mod = importlib.import_module("src.core.governance.prana_service")

    budgets = await prana_service_mod.PranaService(db).get_balances(tenant_id)
    return PranaBudgetsResponse(
        tenant_id=tenant_id,
        budgets=[
            PranaDepartmentBudgetEntry(
                department=b.department,
                total_prana=b.total_prana,
                spent_prana=b.spent_prana,
                available=b.total_prana - b.spent_prana,
            )
            for b in budgets
        ],
    )


@router.post("/allocate", response_model=EmergencyAllocationResponse)
async def allocate_emergency_prana(
    body: EmergencyAllocationRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    authorized_by: int = Depends(require_scopes(OAuth2Scope.PRANA_MANAGE)),
) -> EmergencyAllocationResponse:
    """Emergency prana allocation to a department (ADR-021). Requires the PRANA_MANAGE scope;
    ``authorized_by`` is the verified caller id (never client-supplied)."""
    # Dynamisch via importlib (i.p.v. `from ... import`) om deze API-laag niet direct aan
    # governance te koppelen (ADR-033) -- zie test_dsm002_dag6_zero_violations.py.
    import importlib

    prana_service_mod = importlib.import_module("src.core.governance.prana_service")

    try:
        result = await prana_service_mod.PranaService(db).allocate_emergency(
            tenant_id,
            body.department,
            body.amount,
            authorized_by=authorized_by,
            reason=body.reason,
        )
        await db.commit()
    except prana_service_mod.PranaBudgetNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"No prana budget for department '{body.department}'"
        ) from exc
    return EmergencyAllocationResponse(
        success=True,
        department=result.department,
        amount=body.amount,
        balance_after=result.balance_after,
    )
