"""Gatekeeper decisions router aEUR" decision listing, chain verification, stats."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import logging
from typing import TYPE_CHECKING, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.api.v1.gatekeeper.dependencies import (
    GatekeeperDecision,
    GatekeeperRepository,
    HITLRequestModel,
)
from src.core.api.v1.gatekeeper.schemas import (
    ChainVerificationResponse,
    DecisionListResponse,
    DecisionResponse,
    ErrorResponse,
    GatekeeperStatsResponse,
)
from src.core.middleware.tenant_context import get_tenant_id

logger = logging.getLogger("gatekeeper_api")

router = APIRouter(prefix="/api/v1/gatekeeper", tags=["Gatekeeper"])


if TYPE_CHECKING:
    pass  # GatekeeperDecision moved to module-level import


def _db_record_to_response(record: "GatekeeperDecision") -> DecisionResponse:
    """Convert database record to API response."""
    return DecisionResponse(
        decision_id=record.decision_id,
        task_id=record.task_id,
        decision=record.decision,
        risk_category=record.risk_category,
        risk_level=record.risk_level,
        hitl_required=record.hitl_required,
        hitl_ticket_ref=record.hitl_ticket_ref,
        decision_hash=record.decision_hash,
        previous_hash=record.previous_hash,
        timestamp=record.timestamp,
    )


@router.get(
    "/decisions",
    response_model=DecisionListResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def list_decisions(
    request: Request,
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    task_id: str | None = Query(None, description="Filter by task ID"),
    db: AsyncSession = Depends(get_db),
) -> DecisionListResponse:
    """List Gatekeeper decisions for the current tenant."""
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")

    query = select(GatekeeperDecision).where(GatekeeperDecision.tenant_id == tenant_id)
    if task_id:
        query = query.where(GatekeeperDecision.task_id == task_id)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(GatekeeperDecision.timestamp.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    records = result.scalars().all()

    logger.info(
        "list_decisions",
        extra={"tenant_id": tenant_id, "limit": limit, "offset": offset, "count": len(records)},
    )

    return DecisionListResponse(
        data=[_db_record_to_response(r) for r in records],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/decisions/{task_id}",
    response_model=list[DecisionResponse],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
async def get_decisions_by_task(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> list[DecisionResponse]:
    """Get all decisions for a specific task."""
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")

    repo = GatekeeperRepository(db, tenant_id)

    decisions = await repo.get_decisions_by_task(task_id)
    if not decisions:
        raise HTTPException(status_code=404, detail="No decisions found for the specified task")

    return [_db_record_to_response(d) for d in decisions]


@router.get(
    "/decisions/{task_id}/chain",
    response_model=ChainVerificationResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def verify_task_chain(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ChainVerificationResponse:
    """Verify the hash chain integrity for a task's decisions."""
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")

    repo = GatekeeperRepository(db, tenant_id)

    decisions = await repo.get_decisions_by_task(task_id)
    if not decisions:
        return ChainVerificationResponse(
            task_id=task_id,
            chain_valid=True,
            decisions_count=0,
            first_decision=None,
            last_decision=None,
        )

    chain_valid = True
    for i in range(1, len(decisions)):
        if decisions[i].previous_hash != decisions[i - 1].decision_hash:
            chain_valid = False
            break

    return ChainVerificationResponse(
        task_id=task_id,
        chain_valid=chain_valid,
        decisions_count=len(decisions),
        first_decision=decisions[0].decision_id,
        last_decision=decisions[-1].decision_id,
    )


@router.get(
    "/stats",
    response_model=GatekeeperStatsResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> GatekeeperStatsResponse:
    """Get Gatekeeper statistics for the current tenant."""
    tenant_id = get_tenant_id()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")

    repo = GatekeeperRepository(db, tenant_id)

    decisions_query = (
        select(GatekeeperDecision.decision, func.count())
        .where(GatekeeperDecision.tenant_id == tenant_id)
        .group_by(GatekeeperDecision.decision)
    )
    decisions_result = await db.execute(decisions_query)
    decision_counts = {d: c for d, c in decisions_result.all()}

    require_hitl_query = select(func.count()).where(
        (GatekeeperDecision.tenant_id == tenant_id) & (GatekeeperDecision.hitl_required.is_(True))
    )
    require_hitl_result = await db.execute(require_hitl_query)
    require_hitl_count = require_hitl_result.scalar_one() or 0

    hitl_query = (
        select(HITLRequestModel.status, func.count())
        .where(HITLRequestModel.tenant_id == tenant_id)
        .group_by(HITLRequestModel.status)
    )
    hitl_result = await db.execute(hitl_query)
    hitl_counts = {s: c for s, c in hitl_result.all()}

    chain_integrity = await repo.verify_chain_integrity()
    total_decisions = sum(decision_counts.values())

    logger.info(
        "get_stats",
        extra={
            "tenant_id": tenant_id,
            "total_decisions": total_decisions,
            "chain_integrity": chain_integrity,
        },
    )

    return GatekeeperStatsResponse(
        total_decisions=total_decisions,
        allowed=decision_counts.get("allow", 0),
        blocked=decision_counts.get("block", 0),
        require_hitl=require_hitl_count,
        hitl_pending=hitl_counts.get("pending", 0),
        hitl_approved=hitl_counts.get("approved", 0),
        hitl_rejected=hitl_counts.get("rejected", 0),
        chain_integrity=chain_integrity,
    )
