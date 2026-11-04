"""
Sync JSON Router - Workflow snapshot and awareness endpoints.

Provides:
- PUT /sync/snapshot/{workflow_id}  (JSON snapshot save)
- GET /sync/snapshot/{workflow_id}  (JSON snapshot retrieve)
- GET /sync/awareness/{workflow_id} (Redis awareness list)

ASCII-only, no emojis (CLAUDE.md Section 10).
NOTE: Do NOT add `from __future__ import annotations` here.
      The `@snapshot_write_limit` / `@snapshot_read_limit` decorators
      use `@functools.wraps` which breaks FastAPI body introspection
      when combined with deferred annotations (CLAUDE.md known pitfalls).
"""
# orphan:exempt -- registered dynamically via importlib in workflows registry

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.sync.schemas import (
    AwarenessResponse,
    SnapshotRequest,
    SnapshotResponse,
)
from src.core.auth.api_deps import get_current_user
from src.core.middleware.tenant_context import require_tenant_id
from .dependencies import (
    get_db,
    get_redis_client,
    CollaborationSnapshot,
    snapshot_read_limit,
    snapshot_write_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])

# ---------------------------------------------------------------------------
# Snapshot endpoints
# ---------------------------------------------------------------------------


@router.put(
    "/snapshot/{workflow_id}",
    response_model=SnapshotResponse,
    status_code=status.HTTP_200_OK,
)
@snapshot_write_limit
async def save_json_snapshot(
    request: Request,
    workflow_id: str = Path(
        ...,
        min_length=1,
        max_length=200,
        pattern=r"^[\w\-]+$",
        description="Workflow identifier",
    ),
    data: SnapshotRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Save a JSON workflow snapshot for real-time collaboration."""
    logger.info(
        "sync_snapshot_save: workflow_id=%s tenant_id=%s user_id=%s",
        workflow_id,
        tenant_id,
        getattr(current_user, "id", None),
    )

    snapshot = CollaborationSnapshot(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        snapshot_data=data.model_dump(),
        version=data.version,
    )
    db.add(snapshot)

    # Retention: keep max 100 snapshots per tenant + workflow (FA-002)
    stale_ids_query = (
        select(CollaborationSnapshot.id)
        .where(
            CollaborationSnapshot.tenant_id == tenant_id,
            CollaborationSnapshot.workflow_id == workflow_id,
        )
        .order_by(CollaborationSnapshot.created_at.desc())
        .offset(100)
    )
    await db.execute(
        delete(CollaborationSnapshot).where(CollaborationSnapshot.id.in_(stale_ids_query))
    )

    await db.commit()

    logger.info(
        "sync_snapshot_saved: workflow_id=%s tenant_id=%s user_id=%s",
        workflow_id,
        tenant_id,
        getattr(current_user, "id", None),
    )

    return {
        "success": True,
        "data": {
            "workflow_id": workflow_id,
            "saved": True,
            "version": data.version,
        },
    }


@router.get(
    "/snapshot/{workflow_id}",
    response_model=SnapshotResponse,
)
@snapshot_read_limit
async def get_json_snapshot(
    request: Request,
    workflow_id: str = Path(
        ...,
        min_length=1,
        max_length=200,
        pattern=r"^[\w\-]+$",
        description="Workflow identifier",
    ),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Retrieve the most recent JSON workflow snapshot."""
    logger.info(
        "sync_snapshot_get: workflow_id=%s tenant_id=%s user_id=%s",
        workflow_id,
        tenant_id,
        getattr(current_user, "id", None),
    )

    result = await db.execute(
        select(CollaborationSnapshot)
        .where(
            CollaborationSnapshot.tenant_id == tenant_id,
            CollaborationSnapshot.workflow_id == workflow_id,
        )
        .order_by(CollaborationSnapshot.created_at.desc())
        .limit(1)
    )
    snapshot = result.scalar_one_or_none()

    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": {
                    "code": "SNAPSHOT_NOT_FOUND",
                    "message": f"No snapshot found for workflow {workflow_id}",
                },
            },
        )

    return {
        "success": True,
        "data": snapshot.snapshot_data,
    }


# ---------------------------------------------------------------------------
# Awareness endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/awareness/{workflow_id}",
    response_model=AwarenessResponse,
)
@snapshot_read_limit
async def get_sync_awareness(
    request: Request,
    workflow_id: str = Path(
        ...,
        min_length=1,
        max_length=200,
        pattern=r"^[\w\-]+$",
        description="Workflow identifier",
    ),
    tenant_id: int = Depends(require_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get active users for a workflow from Redis awareness hash."""
    logger.info(
        "sync_awareness_get: workflow_id=%s tenant_id=%s user_id=%s",
        workflow_id,
        tenant_id,
        getattr(current_user, "id", None),
    )

    awareness_key = f"awareness:{tenant_id}:{workflow_id}"
    users: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    try:
        redis_client = await get_redis_client()
        raw_data = await redis_client.hgetall(awareness_key)  # pyright: ignore
        for user_id, user_json in raw_data.items():
            try:
                users.append(json.loads(user_json))
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    "sync_awareness_bad_json: key=%s field=%s",
                    awareness_key,
                    user_id,
                )
    except Exception as exc:
        logger.warning(
            "sync_awareness_redis_failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        # Graceful degradation: return empty list on Redis failure
        users = []

    return {
        "success": True,
        "data": users,
    }
