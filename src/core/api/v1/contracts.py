"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
A2A Contracts REST API.

Exposes the in-memory ContractManager for listing and proposing
agent-to-agent contracts. No database access; state is per-tenant in-memory.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from src.core.api.dependencies import require_authenticated_user
from src.core.api.v1._prana_contracts_cache import get_contract_manager
from src.core.middleware.tenant_context import safe_get_tenant_id

router = APIRouter(prefix="/contracts", tags=["A2A Contracts"])


class ContractResponse(BaseModel):
    contract_id: str
    producer_agent: str
    consumer_agent: str
    producer_department: str
    consumer_department: str
    prana_cost: int
    deadline_ms: int
    status: str
    created_at: str
    agreed_at: str | None
    completed_at: str | None


class ContractListResponse(BaseModel):
    tenant_id: int
    contracts: list[ContractResponse]
    total: int
    limit: int
    offset: int


class ProposeContractRequest(BaseModel):
    consumer_agent: str = Field(min_length=1, max_length=128)
    producer_agent: str = Field(min_length=1, max_length=128)
    consumer_department: str = Field(min_length=1, max_length=64)
    producer_department: str = Field(min_length=1, max_length=64)
    required_data: dict[str, str] = Field(default_factory=dict)
    deadline_ms: int = Field(default=5000, gt=0, le=60000)
    prana_cost: int = Field(default=50, gt=0, le=10000)

    @field_validator("required_data")
    @classmethod
    def validate_required_data_size(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 50:
            raise ValueError("required_data may not contain more than 50 fields")
        for key, val in v.items():
            if len(key) > 256 or len(val) > 256:
                raise ValueError("required_data keys and values must be at most 256 characters")
        return v


class ProposeContractResponse(BaseModel):
    success: bool
    contract_id: str
    status: str


@router.get("", response_model=ContractListResponse)
async def list_contracts(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tenant_id: int = Depends(safe_get_tenant_id),
    _user: dict[str, Any] = Depends(require_authenticated_user),  # TODO(TYPE): replace Any with concrete type
) -> ContractListResponse:
    """List paginated A2A contracts for the active tenant."""
    manager = get_contract_manager(tenant_id)
    all_contracts = [
        ContractResponse(
            contract_id=c.contract_id,
            producer_agent=c.producer_agent,
            consumer_agent=c.consumer_agent,
            producer_department=c.producer_department.value,
            consumer_department=c.consumer_department.value,
            prana_cost=c.prana_cost,
            deadline_ms=c.deadline_ms,
            status=c.status.value,
            created_at=c.created_at.isoformat(),
            agreed_at=c.agreed_at.isoformat() if c.agreed_at else None,
            completed_at=c.completed_at.isoformat() if c.completed_at else None,
        )
        for c in manager._contracts.values()
    ]
    paginated = all_contracts[offset : offset + limit]
    return ContractListResponse(
        tenant_id=tenant_id,
        contracts=paginated,
        total=len(all_contracts),
        limit=limit,
        offset=offset,
    )


@router.post("/propose", response_model=ProposeContractResponse, status_code=201)
async def propose_contract(
    request: ProposeContractRequest,
    tenant_id: int = Depends(safe_get_tenant_id),
    _user: dict[str, Any] = Depends(require_authenticated_user),  # TODO(TYPE): replace Any with concrete type
) -> ProposeContractResponse:
    """Propose a new A2A contract between two agents."""
    from src.core.api.v1.contracts_dependencies import Department

    try:
        consumer_dept = Department(request.consumer_department)
        producer_dept = Department(request.producer_department)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid department") from e

    manager = get_contract_manager(tenant_id)
    contract = await manager.propose_contract(
        consumer_agent=request.consumer_agent,
        producer_agent=request.producer_agent,
        consumer_dept=consumer_dept,
        producer_dept=producer_dept,
        required_data=request.required_data,
        deadline_ms=request.deadline_ms,
        prana_cost=request.prana_cost,
    )
    return ProposeContractResponse(
        success=True,
        contract_id=contract.contract_id,
        status=contract.status.value,
    )
