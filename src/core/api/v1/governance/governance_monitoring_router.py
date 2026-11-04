"""Governance monitoring router -- alerts, accuracy, risk-register."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.api.v1.governance.dependencies import (
    AccuracyMonitor,
    GovernanceAlert,
    RiskEntry,
    governance_read_limit,
)
from src.core.auth.api_deps import OAuth2Scope, require_scopes
from src.core.middleware.tenant_context import get_current_tenant_id

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

# Module-level dependency so tests can override via app.dependency_overrides
_require_governance_read = require_scopes(OAuth2Scope.GOVERNANCE_READ)


@router.get("/alerts")
@governance_read_limit
async def list_alerts(
    request: Request,
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(_require_governance_read),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Art. 15: List governance alerts for the current tenant."""
    from sqlalchemy import func, select

    query = select(GovernanceAlert).where(GovernanceAlert.tenant_id == tenant_id)
    count_query = (
        select(func.count())
        .select_from(GovernanceAlert)
        .where(GovernanceAlert.tenant_id == tenant_id)
    )
    if severity is not None:
        query = query.where(GovernanceAlert.severity == severity)
        count_query = count_query.where(GovernanceAlert.severity == severity)
    if acknowledged is not None:
        query = query.where(GovernanceAlert.acknowledged == acknowledged)
        count_query = count_query.where(GovernanceAlert.acknowledged == acknowledged)

    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    alerts = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "id": str(a.id),
                "tenant_id": a.tenant_id,
                "agent_name": a.agent_name,
                "violation_type": a.violation_type,
                "severity": a.severity,
                "acknowledged": a.acknowledged,
                "created_at": a.created_at.isoformat() if a.created_at is not None else None,
            }
            for a in alerts
        ],
        "limit": limit,
        "offset": offset,
        "total_count": total_count,
    }


@router.get("/accuracy/{agent_name}")
@governance_read_limit
async def get_accuracy_report(
    request: Request,
    agent_name: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(_require_governance_read),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Art. 15: Accuracy drift report per agent."""
    monitor = AccuracyMonitor(db)
    drift = await monitor.check_drift(tenant_id, agent_name)
    return {
        "success": True,
        "data": {
            "agent_name": agent_name,
            "drift": drift,
        },
    }


@router.get("/risk-register")
@governance_read_limit
async def list_risk_entries(
    request: Request,
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(_require_governance_read),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Art. 9: Risk register entries for the current tenant."""
    from sqlalchemy import func, select

    count_query = (
        select(func.count()).select_from(RiskEntry).where(RiskEntry.tenant_id == tenant_id)
    )
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    result = await db.execute(
        select(RiskEntry).where(RiskEntry.tenant_id == tenant_id).limit(limit).offset(offset)
    )
    entries = result.scalars().all()

    return {
        "success": True,
        "data": [
            {
                "id": str(e.id),
                "agent_name": e.agent_name,
                "likelihood": e.likelihood,
                "impact": e.impact,
                "residual_risk": e.residual_risk,
                "mitigation": e.mitigation,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
        "limit": limit,
        "offset": offset,
        "total_count": total_count,
    }
