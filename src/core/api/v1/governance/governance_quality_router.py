"""Governance quality router aEUR" quality-check, authority-reports."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.api.v1.governance.dependencies import (
    AuthorityReport,
    QualityGate,
    governance_read_limit,
    governance_write_limit,
)
from src.core.auth.api_deps import get_current_user
from src.core.middleware.tenant_context import get_current_tenant_id

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])


@router.post("/quality-check/{agent_name}")
@governance_write_limit
async def run_quality_check(
    request: Request,
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Art. 17: Run pre-deployment quality gate for an agent."""
    gate = QualityGate(db)
    results = await gate.pre_deployment_check(
        tenant_id=tenant_id,
        agent_name=agent_name,
        user_id=current_user.id,
    )
    return {
        "success": True,
        "data": {
            "agent_name": agent_name,
            "checks": results,
        },
    }


@router.get("/authority-reports")
@governance_read_limit
async def list_authority_reports(
    request: Request,
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Art. 72: Surveillance authority reports for the current tenant."""
    from sqlalchemy import func, select

    count_query = (
        select(func.count())
        .select_from(AuthorityReport)
        .where(AuthorityReport.tenant_id == tenant_id)
    )
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    result = await db.execute(
        select(AuthorityReport)
        .where(AuthorityReport.tenant_id == tenant_id)
        .limit(limit)
        .offset(offset)
    )
    reports = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "id": str(r.id),
                "report_type": r.report_type,
                "authority_name": r.authority_name,
                "submitted_at": r.submitted_at.isoformat() if r.submitted_at is not None else None,
                "created_at": r.created_at.isoformat() if r.created_at is not None else None,
            }
            for r in reports
        ],
        "limit": limit,
        "offset": offset,
        "total_count": total_count,
    }
