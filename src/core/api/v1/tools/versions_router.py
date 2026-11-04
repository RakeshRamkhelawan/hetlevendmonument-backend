# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Tools version history endpoint (ADR-033 Laag 1)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.tools.dependencies import get_current_user, get_db
from src.core.api.v1.tools.schemas import (
    ToolVersionListResponse,
    ToolVersionResponse,
)
from src.core.models.rbac_models import User
from src.core.tool_broker.models import Tool, ToolVersion

logger = logging.getLogger(__name__)

versions_router = APIRouter()


@versions_router.get(
    "/{tool_id}/versions",
    response_model=ToolVersionListResponse,
    summary="Get tool version history",
)
async def get_tool_versions(
    tool_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolVersionListResponse:
    owner = await db.execute(
        select(Tool.id).where(
            Tool.id == tool_id,
            Tool.tenant_id == current_user.tenant_id,
        )
    )
    if owner.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Tool {tool_id} not found",
        )

    version_where = (
        ToolVersion.tool_id == tool_id,
        ToolVersion.tenant_id == current_user.tenant_id,
    )
    count_result = await db.execute(
        select(func.count()).select_from(select(ToolVersion).where(*version_where).subquery())
    )
    total = count_result.scalar_one()

    rows = await db.execute(
        select(ToolVersion)
        .where(*version_where)
        .order_by(ToolVersion.version.desc())
        .offset(skip)
        .limit(limit)
    )
    versions = rows.scalars().all()

    page = (skip // limit) + 1 if limit > 0 else 1
    return ToolVersionListResponse(
        data=[
            ToolVersionResponse(
                id=v.id,
                tool_id=v.tool_id,
                version=v.version,
                snapshot=v.snapshot,
                created_at=v.created_at,
            )
            for v in versions
        ],
        total=total,
        page=page,
        per_page=limit,
    )
