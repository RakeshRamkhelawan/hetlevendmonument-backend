# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
from collections.abc import Sequence
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.admin_learning_schemas import (
    GDPRDeleteUserRequest,
    GDPRExportUserRequest,
    GDPRRetentionRequest,
)
from src.core.api.dependencies import require_admin_role
from src.core.auth import UserResponse
from src.core.api.admin_learning_endpoints_dependencies import (
    AuditLog,
    LearningBudgetService,
    LearningGDPRService,
    consent_read_limit,
    consent_update_limit,
    get_db,
)


async def _read_learning_audit_log(
    tenant_id: int, limit: int, offset: int, session: AsyncSession
) -> Sequence[Any]:  # TODO(TYPE): replace Any with concrete type
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


router = APIRouter(prefix="/admin/learning", tags=["admin-learning"])


def _resolve_tenant_id(current_user: UserResponse) -> int:
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None and isinstance(current_user, dict):
        tenant_id = current_user.get("tenant_id")
    if tenant_id is None:
        raise ValueError("tenant_id is required; admin operations require explicit tenant context.")
    return int(tenant_id)


def _resolve_user_id(current_user: UserResponse) -> int | None:
    user_id = getattr(current_user, "id", None)
    if user_id is None and isinstance(current_user, dict):
        user_id = current_user.get("id")
    return int(user_id) if user_id is not None else None


def _is_system_admin(current_user: UserResponse) -> bool:
    """Check if user has system_admin role (platform-wide access)."""
    user_roles = getattr(current_user, "roles", []) or []
    return "system_admin" in user_roles


def _enforce_tenant_access(
    requested_tenant_id: int,
    current_user: UserResponse,
) -> None:
    """Enforce that a non-system-admin can only access their own tenant.

    Raises HTTPException 403 if the user tries to access another tenant's data.
    """
    if _is_system_admin(current_user):
        return
    user_tenant_id = _resolve_tenant_id(current_user)
    if requested_tenant_id != user_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own tenant's resources.",
        )


@router.get("/status")
async def get_learning_status(
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    service = LearningGDPRService(db, audit_log_reader=_read_learning_audit_log)
    report = await service.get_status(tenant_id=_resolve_tenant_id(current_user))
    return report.model_dump()


@router.get("/audit-log")
async def get_learning_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    service = LearningGDPRService(db, audit_log_reader=_read_learning_audit_log)
    tenant_id = _resolve_tenant_id(current_user)
    entries = await service.get_audit_log(tenant_id=tenant_id, limit=limit, offset=offset)
    return {
        "tenant_id": tenant_id,
        "items": [entry.model_dump() for entry in entries],
        "total": len(entries),
    }


@router.post("/gdpr/delete-user")
@consent_update_limit
async def delete_learning_user_data(
    http_request: Request,
    request: GDPRDeleteUserRequest,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    service = LearningGDPRService(db, audit_log_reader=_read_learning_audit_log)
    report = await service.delete_user_data(
        user_id=request.user_id,
        tenant_id=_resolve_tenant_id(current_user),
        requested_by_user_id=_resolve_user_id(current_user),
        reason=request.reason,
    )
    return report.model_dump()


@router.post("/gdpr/export-user")
@consent_update_limit
async def export_learning_user_data(
    http_request: Request,
    request: GDPRExportUserRequest,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    service = LearningGDPRService(db, audit_log_reader=_read_learning_audit_log)
    export = await service.export_user_data(
        user_id=request.user_id,
        tenant_id=_resolve_tenant_id(current_user),
        requested_by_user_id=_resolve_user_id(current_user),
    )
    return export.model_dump()


@router.post("/gdpr/retention")
@consent_update_limit
async def apply_learning_retention_policy(
    http_request: Request,
    request: GDPRRetentionRequest,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    service = LearningGDPRService(db, audit_log_reader=_read_learning_audit_log)
    report = await service.apply_retention_policy(
        max_age_days=request.max_age_days,
        tenant_id=_resolve_tenant_id(current_user),
        requested_by_user_id=_resolve_user_id(current_user),
    )
    return report.model_dump()


# =============================================================================
# Tenant LLM Budget Admin Endpoints (ADR-026 par. 1.2.2)
# =============================================================================


class TenantLLMBudgetResponse(BaseModel):
    """Response schema for tenant LLM budget."""

    tenant_id: int
    month: str
    budget_eur_soft: float
    budget_eur_hard: float
    spent_eur: float
    remaining_soft: float
    remaining_hard: float
    created_at: str | None = None
    updated_at: str | None = None


class TenantLLMBudgetUpdateRequest(BaseModel):
    """Request schema for updating tenant LLM budget."""

    budget_eur_soft: float = Field(..., ge=0, le=100000, description="Soft cap in EUR")
    budget_eur_hard: float = Field(..., ge=0, le=100000, description="Hard cap in EUR")

    @field_validator("budget_eur_hard")
    @classmethod
    def hard_cap_must_be_gte_soft_cap(
        cls,
        v: float,
        info: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> float:  # TODO(TYPE): replace Any with concrete type
        """Ensure hard cap is >= soft cap."""
        data = info.data
        soft = data.get("budget_eur_soft")
        if soft is not None and v < soft:
            raise ValueError("budget_eur_hard must be greater than or equal to budget_eur_soft")
        return v


@router.get(
    "/tenants/{tenant_id}/llm-budget",
    response_model=TenantLLMBudgetResponse,
    summary="Get tenant LLM budget for current month",
)
@consent_read_limit
async def get_tenant_llm_budget(
    request: Request,
    tenant_id: int,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> TenantLLMBudgetResponse:
    """Get the current month's LLM budget for a tenant."""
    _enforce_tenant_access(tenant_id, current_user)
    service = LearningBudgetService(db)
    data = await service.get_budget(tenant_id)
    return TenantLLMBudgetResponse(**data)


@router.put(
    "/tenants/{tenant_id}/llm-budget",
    response_model=TenantLLMBudgetResponse,
    summary="Update tenant LLM budget for current month",
)
@consent_update_limit
async def update_tenant_llm_budget(
    http_request: Request,
    tenant_id: int,
    request: TenantLLMBudgetUpdateRequest,
    current_user: UserResponse = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db),
) -> TenantLLMBudgetResponse:
    """Update (or create) the current month's LLM budget for a tenant."""
    _enforce_tenant_access(tenant_id, current_user)
    service = LearningBudgetService(db)
    data = await service.update_budget(
        tenant_id=tenant_id,
        budget_eur_soft=request.budget_eur_soft,
        budget_eur_hard=request.budget_eur_hard,
    )
    return TenantLLMBudgetResponse(**data)
