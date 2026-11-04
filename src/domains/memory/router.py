"""
Agent Memory Router -- Digital Twin API
=======================================

FastAPI router for the persistent memory / digital twin layer.
Prefix: /api/v1/agent-memory

Endpoints:
  Profile:
    GET    /profiles/{agent_id}          -- get agent memory profile
    POST   /profiles                     -- create/upsert profile
    PATCH  /profiles/{agent_id}          -- partial update

  Memory items:
    POST   /items                        -- write single candidate
    POST   /items/bulk                   -- write multiple candidates
    GET    /items                        -- list items (paginated)
    PATCH  /items/{item_id}/status       -- accept/archive/flag
    DELETE /items/{item_id}              -- soft-delete

  Retrieval:
    POST   /query                        -- hybrid retrieval query
    GET    /boot-context/{agent_id}      -- build session boot context

  Events:
    POST   /events                       -- log a session event

  Stats:
    GET    /stats                        -- tenant memory statistics

Security: All endpoints require JWT + workflows:read or workflows:write scope.
Tenant isolation: tenant_id always from JWT, never from client payload.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import get_db
from src.core.auth.scope_validator import require_scopes
from src.core.auth.scopes import OAuth2Scope
from src.core.middleware.tenant_context import get_current_tenant_id
from src.domains.memory.models import (
    AgentMemoryProfile,
    MemoryConsolidationRun,
    MemoryItem,
    SessionMemoryEvent,
)
from src.domains.memory.schemas import (
    AgentMemoryProfileCreate,
    AgentMemoryProfileResponse,
    AgentMemoryProfileUpdate,
    BootContextResponse,
    ConsolidationRunResponse,
    MemoryItemBulkWrite,
    MemoryItemResponse,
    MemoryItemStatusUpdate,
    MemoryItemWrite,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MemoryStatsResponse,
    SessionEventResponse,
    SessionEventWrite,
)
from src.domains.memory.services.consolidation_worker import MemoryConsolidationWorker
from src.domains.memory.services.context_packer_service import ContextPackerService
from src.domains.memory.services.drift_engine import ProfileDriftEngine
from src.domains.memory.services.memory_retrieval_service import MemoryRetrievalService
from src.domains.memory.services.memory_write_service import MemoryWriteService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent-memory", tags=["Agent Memory"])


# ===========================================================================
# Dependency helpers
# ===========================================================================


async def _get_tenant(
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_READ)
    ),  # TODO(TYPE): replace Any with concrete type
) -> int:
    """Extract and validate tenant_id from JWT context."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


async def _get_write_tenant(
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_WRITE)
    ),  # TODO(TYPE): replace Any with concrete type
) -> int:
    """Require write scope and return tenant_id."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required.",
        )
    return tenant_id


# ===========================================================================
# Profile endpoints
# ===========================================================================


@router.get(
    "/profiles/{agent_id}",
    response_model=AgentMemoryProfileResponse,
    summary="Get agent memory profile",
)
async def get_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
) -> AgentMemoryProfileResponse:
    """
    Retrieve the active memory profile for a specific agent.

    Returns identity, goals, operating rules, and domain expertise.
    """
    result = await db.execute(
        select(AgentMemoryProfile).where(
            AgentMemoryProfile.tenant_id == tenant_id,
            AgentMemoryProfile.agent_id == agent_id,
            AgentMemoryProfile.is_active.is_(True),
            AgentMemoryProfile.deleted_at.is_(None),
        )
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active memory profile found for agent '{agent_id}'",
        )

    return AgentMemoryProfileResponse.model_validate(profile)


@router.post(
    "/profiles",
    response_model=AgentMemoryProfileResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or upsert agent memory profile",
)
async def upsert_profile(
    payload: AgentMemoryProfileCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> AgentMemoryProfileResponse:
    """
    Create or update an agent memory profile.

    If a profile already exists for this agent/tenant, it is updated
    and the version counter is incremented.
    """
    packer = ContextPackerService(db=db, tenant_id=tenant_id)
    profile = await packer.upsert_profile(
        agent_id=payload.agent_id,
        agent_type=payload.agent_type,
        persona_name=payload.persona_name,
        persona_description=payload.persona_description,
        active_goals=[g.model_dump() for g in payload.active_goals],
        operating_rules=[r.model_dump() for r in payload.operating_rules],
        domain_expertise=[e.model_dump() for e in payload.domain_expertise],
        owner_user_id=payload.owner_user_id,
    )
    await db.commit()
    return AgentMemoryProfileResponse.model_validate(profile)


@router.patch(
    "/profiles/{agent_id}",
    response_model=AgentMemoryProfileResponse,
    summary="Partial update of agent memory profile",
)
async def update_profile(
    agent_id: str,
    payload: AgentMemoryProfileUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> AgentMemoryProfileResponse:
    """Partially update a profile -- only provided fields are changed."""
    packer = ContextPackerService(db=db, tenant_id=tenant_id)

    update_kwargs = payload.model_dump(exclude_none=True)
    # Serialise nested models if present
    for key in ("active_goals", "operating_rules", "domain_expertise"):
        if key in update_kwargs and isinstance(update_kwargs[key], list):
            update_kwargs[key] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in update_kwargs[key]
            ]

    profile = await packer.upsert_profile(agent_id=agent_id, **update_kwargs)
    await db.commit()
    return AgentMemoryProfileResponse.model_validate(profile)


# ===========================================================================
# Memory item endpoints
# ===========================================================================


@router.post(
    "/items",
    response_model=MemoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Write a memory candidate",
)
async def write_memory_item(
    payload: MemoryItemWrite,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> MemoryItemResponse:
    """
    Write a single memory candidate.

    Status defaults to 'proposed'. Exact duplicates are silently skipped
    and the existing item is returned.

    Security: tenant_id is injected from JWT -- cannot be spoofed.
    """
    service = MemoryWriteService(db=db, tenant_id=tenant_id)
    item = await service.write(payload)
    await db.commit()
    return MemoryItemResponse.model_validate(item)


@router.post(
    "/items/bulk",
    response_model=list[MemoryItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Bulk write memory candidates",
)
async def bulk_write_memory_items(
    payload: MemoryItemBulkWrite,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> list[MemoryItemResponse]:
    """
    Write up to 50 memory candidates in a single transaction.
    Duplicates are skipped. Returns all items (new + existing duplicates).
    """
    service = MemoryWriteService(db=db, tenant_id=tenant_id)
    items = await service.bulk_write(payload.items)
    await db.commit()
    return [MemoryItemResponse.model_validate(i) for i in items]


@router.get(
    "/items",
    response_model=list[MemoryItemResponse],
    summary="List memory items (paginated)",
)
async def list_memory_items(
    agent_id: str | None = Query(None, description="Filter by agent"),
    memory_type: str | None = Query(None, description="Filter by type"),
    status_filter: str | None = Query("accepted", description="Item status"),
    privacy_scope: str | None = Query(None, description="Privacy scope filter"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
) -> list[MemoryItemResponse]:
    """
    Paginated list of memory items for the authenticated tenant.
    """
    from sqlalchemy import desc

    stmt = select(MemoryItem).where(
        MemoryItem.tenant_id == tenant_id,
        MemoryItem.deleted_at.is_(None),
    )

    if agent_id:
        stmt = stmt.where(MemoryItem.agent_id == agent_id)
    if memory_type:
        stmt = stmt.where(MemoryItem.memory_type == memory_type)
    if status_filter:
        stmt = stmt.where(MemoryItem.status == status_filter)
    if privacy_scope:
        stmt = stmt.where(MemoryItem.privacy_scope == privacy_scope)

    stmt = (
        stmt.order_by(desc(MemoryItem.created_at)).offset((page - 1) * page_size).limit(page_size)
    )

    result = await db.execute(stmt)
    items = result.scalars().all()
    return [MemoryItemResponse.model_validate(i) for i in items]


@router.patch(
    "/items/{item_id}/status",
    response_model=MemoryItemResponse,
    summary="Update memory item status",
)
async def update_item_status(
    item_id: int,
    payload: MemoryItemStatusUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> MemoryItemResponse:
    """
    Transition a memory item to accepted, archived, or contradicted.

    Use this to review proposed items and promote them to active memory.
    """
    service = MemoryWriteService(db=db, tenant_id=tenant_id)
    item = await service.update_item_status(item_id, payload.status)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory item {item_id} not found",
        )
    await db.commit()
    return MemoryItemResponse.model_validate(item)


@router.delete(
    "/items/{item_id}",
    status_code=status.HTTP_200_OK,
    summary="Soft-delete a memory item",
    response_class=Response,
)
async def delete_memory_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> None:
    """
    Soft-delete a memory item (sets deleted_at timestamp).
    The item remains in the database for audit purposes.
    """
    service = MemoryWriteService(db=db, tenant_id=tenant_id)
    deleted = await service.soft_delete_item(item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory item {item_id} not found",
        )
    await db.commit()


# ===========================================================================
# Retrieval endpoints
# ===========================================================================


@router.post(
    "/query",
    response_model=MemoryQueryResponse,
    summary="Hybrid memory retrieval",
)
async def query_memory(
    payload: MemoryQueryRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
) -> MemoryQueryResponse:
    """
    Retrieve relevant memory items for a given query.

    Sprint A: PostgreSQL full-text search + importance/recency ranking.
    Sprint B: pgvector ANN search will be added alongside.

    Results are always scoped to the authenticated tenant.
    """
    service = MemoryRetrievalService(db=db, tenant_id=tenant_id)
    result = await service.query(payload)
    return MemoryQueryResponse(
        items=[MemoryItemResponse.model_validate(i) for i in result["items"]],
        total_candidates=result["total_candidates"],
        query_time_ms=result["query_time_ms"],
        retrieval_method=result["retrieval_method"],
    )


@router.get(
    "/boot-context/{agent_id}",
    response_model=BootContextResponse,
    summary="Build agent session boot context",
)
async def get_boot_context(
    agent_id: str,
    token_budget: int = Query(default=2000, ge=200, le=8000),
    session_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
) -> BootContextResponse:
    """
    Build and return a packed boot context for the given agent.

    This should be called at the start of every agent session.
    The response contains identity, active goals, recent episodes,
    top facts, and preferences -- all within the token budget.
    """
    packer = ContextPackerService(db=db, tenant_id=tenant_id)
    ctx = await packer.build(
        agent_id=agent_id,
        session_id=session_id,
        token_budget=token_budget,
    )

    return BootContextResponse(
        agent_id=ctx["agent_id"],
        tenant_id=ctx["tenant_id"],
        profile=(
            AgentMemoryProfileResponse.model_validate(ctx["profile"]) if ctx["profile"] else None
        ),
        active_goals=ctx["active_goals"],
        recent_episodes=[MemoryItemResponse.model_validate(i) for i in ctx["recent_episodes"]],
        top_facts=[MemoryItemResponse.model_validate(i) for i in ctx["top_facts"]],
        top_preferences=[MemoryItemResponse.model_validate(i) for i in ctx["top_preferences"]],
        estimated_tokens=ctx["estimated_tokens"],
        built_at=ctx["built_at"],
    )


# ===========================================================================
# Session event log
# ===========================================================================


@router.post(
    "/events",
    response_model=SessionEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a session memory event",
)
async def log_session_event(
    payload: SessionEventWrite,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> SessionEventResponse:
    """
    Append an event to the session memory event log.

    Set memory_candidate=true to flag this event for promotion
    to a durable MemoryItem during the next consolidation run.

    This log is append-only and immutable after creation.
    """
    service = MemoryWriteService(db=db, tenant_id=tenant_id)
    event = await service.log_session_event(payload)
    await db.commit()
    return SessionEventResponse.model_validate(event)


# ===========================================================================
# Stats endpoint
# ===========================================================================


@router.get(
    "/stats",
    response_model=MemoryStatsResponse,
    summary="Tenant memory statistics",
)
async def get_memory_stats(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
) -> MemoryStatsResponse:
    """
    Returns aggregate statistics for the authenticated tenant's memory layer.
    Useful for monitoring dashboards and health checks.
    """
    # Total counts by status
    status_rows = await db.execute(
        select(MemoryItem.status, func.count(MemoryItem.id))
        .where(
            MemoryItem.tenant_id == tenant_id,
            MemoryItem.deleted_at.is_(None),
        )
        .group_by(MemoryItem.status)
    )
    status_counts: dict[str, int] = {str(row[0]): cast(int, row[1]) for row in status_rows.all()}

    # Counts by type
    type_rows = await db.execute(
        select(MemoryItem.memory_type, func.count(MemoryItem.id))
        .where(
            MemoryItem.tenant_id == tenant_id,
            MemoryItem.status == "accepted",
            MemoryItem.deleted_at.is_(None),
        )
        .group_by(MemoryItem.memory_type)
    )
    by_type: dict[str, int] = {str(row[0]): cast(int, row[1]) for row in type_rows.all()}

    # Counts by agent
    agent_rows = await db.execute(
        select(MemoryItem.agent_id, func.count(MemoryItem.id))
        .where(
            MemoryItem.tenant_id == tenant_id,
            MemoryItem.status == "accepted",
            MemoryItem.deleted_at.is_(None),
            MemoryItem.agent_id.is_not(None),
        )
        .group_by(MemoryItem.agent_id)
    )
    by_agent: dict[str, int] = {str(k): v for k, v in agent_rows.all()}

    # Last consolidation
    last_run_row = await db.execute(
        select(MemoryConsolidationRun.completed_at)
        .where(
            MemoryConsolidationRun.tenant_id == tenant_id,
            MemoryConsolidationRun.status == "completed",
        )
        .order_by(MemoryConsolidationRun.completed_at.desc())
        .limit(1)
    )
    last_consolidation = last_run_row.scalar_one_or_none()

    # Last write
    last_write_row = await db.execute(
        select(MemoryItem.created_at)
        .where(
            MemoryItem.tenant_id == tenant_id,
            MemoryItem.deleted_at.is_(None),
        )
        .order_by(MemoryItem.created_at.desc())
        .limit(1)
    )
    last_write = last_write_row.scalar_one_or_none()

    total = sum(status_counts.values())

    return MemoryStatsResponse(
        tenant_id=tenant_id,
        total_items=total,
        accepted_items=status_counts.get("accepted", 0),
        proposed_items=status_counts.get("proposed", 0),
        archived_items=status_counts.get("archived", 0),
        by_type=by_type,
        by_agent=by_agent,
        last_consolidation=last_consolidation,
        last_write=last_write,
    )


# ===========================================================================
# Consolidation endpoint (Sprint C)
# ===========================================================================


@router.post(
    "/consolidate",
    response_model=ConsolidationRunResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger memory consolidation run",
)
async def run_consolidation(
    agent_id: str | None = Query(None, description="Scope to a specific agent"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> ConsolidationRunResponse:
    """
    Trigger an on-demand memory consolidation run for this tenant.

    Promotes unresolved SessionMemoryEvents to durable MemoryItems,
    archives superseded items, and optionally backfills embeddings.

    Can be called manually or scheduled nightly via cron/Celery.
    """
    worker = MemoryConsolidationWorker(db=db, tenant_id=tenant_id)
    run = await worker.run(agent_id=agent_id)
    await db.commit()
    return ConsolidationRunResponse(
        id=run.id,
        tenant_id=run.tenant_id,
        agent_id=run.agent_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        sessions_processed=run.sessions_processed,
        events_processed=run.events_processed,
        items_created=run.items_created,
        items_archived=run.items_archived,
        contradictions_found=run.contradictions_found,
        error_message=run.error_message,
    )


# ===========================================================================
# Drift detection endpoints (Sprint D)
# ===========================================================================


@router.get(
    "/drift/{agent_id}",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    summary="Detect profile drift for an agent",
)
async def detect_drift(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_tenant),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Compute the current profile drift score for the specified agent.

    Returns:
      - drift_score (0.0-1.0)
      - severity (none | warning | critical)
      - sub-signals: goal_coverage_gap, rule_violation_score, activity_gap_score
      - missing_goals, violated_rules, last_activity
    """
    engine = ProfileDriftEngine(db=db, tenant_id=tenant_id)
    event = await engine.detect(agent_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active profile found for agent '{agent_id}'",
        )
    return event.to_dict()


@router.post(
    "/drift/{agent_id}/re-anchor",
    response_model=dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    status_code=status.HTTP_200_OK,
    summary="Re-anchor drifted agent profile",
)
async def re_anchor_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(_get_write_tenant),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Trigger a re-anchor for the specified agent's profile.

    Detects drift, writes a versioned snapshot documenting the event,
    and bumps the profile_version for audit trail purposes.

    Safe to call even when drift_score < threshold -- it will always
    create a snapshot, but will indicate severity=none in the response.
    """
    engine = ProfileDriftEngine(db=db, tenant_id=tenant_id)
    event = await engine.detect(agent_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active profile found for agent '{agent_id}'",
        )
    result = await engine.re_anchor(event)
    await db.commit()
    return result
