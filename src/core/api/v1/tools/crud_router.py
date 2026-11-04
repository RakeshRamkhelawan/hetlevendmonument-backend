# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Tools CRUD endpoints: create, list, get, update, delete (ADR-033 Laag 1)."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.tools.dependencies import get_current_user, get_db
from src.core.api.v1.tools.schemas import (
    ToolCreate,
    ToolListResponse,
    ToolParameter,
    ToolResponse,
    ToolStatus,
    ToolType,
    ToolUpdate,
)
from src.core.models.rbac_models import User
from src.core.tool_broker.models import Tool, ToolVersion

logger = logging.getLogger(__name__)

crud_router = APIRouter()


def _tool_to_response(tool: Tool) -> ToolResponse:
    """Convert Tool ORM object to ToolResponse."""
    return ToolResponse(
        id=tool.id,
        tenant_id=tool.tenant_id,
        name=tool.name,
        description=tool.description or "",
        tool_type=ToolType(tool.tool_type),
        status=ToolStatus(tool.status or "active"),
        code=tool.code,
        endpoint_url=tool.endpoint_url,
        parameters=[ToolParameter.model_validate(p) for p in (tool.parameters or [])],
        metadata=tool.metadata_ or {},
        tags=tool.tags or [],
        timeout_seconds=tool.timeout_seconds,
        retry_policy=tool.retry_policy or {},
        created_by=tool.created_by,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
        version=tool.version,
        usage_count=tool.usage_count,
    )


@crud_router.post(
    "/",
    response_model=ToolResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a new tool",
)
async def create_tool(
    data: ToolCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolResponse:
    tool = Tool(
        tenant_id=current_user.tenant_id,
        name=data.name,
        description=data.description,
        tool_type=data.tool_type.value,
        code=data.code,
        endpoint_url=data.endpoint_url,
        parameters=[p.model_dump() for p in data.parameters],
        metadata_=data.metadata,
        tags=data.tags,
        timeout_seconds=data.timeout_seconds,
        retry_policy=data.retry_policy,
        created_by=current_user.id,
    )
    db.add(tool)
    await db.commit()
    await db.refresh(tool)
    logger.info("Tool created: %r by user %s", data.name, current_user.id)
    return _tool_to_response(tool)


@crud_router.get(
    "/",
    response_model=ToolListResponse,
    summary="List tools",
)
async def list_tools(
    tool_status: ToolStatus | None = None,
    tool_type: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolListResponse:
    from fastapi import Query

    base = select(Tool).where(
        Tool.tenant_id == current_user.tenant_id,
        Tool.deleted_at.is_(None),
    )
    if tool_status is not None:
        base = base.where(Tool.status == tool_status.value)
    if tool_type is not None:
        base = base.where(Tool.tool_type == tool_type)

    total_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = total_result.scalar_one()

    rows = await db.execute(base.offset(skip).limit(limit))
    tools = rows.scalars().all()

    page = (skip // limit) + 1 if limit > 0 else 1
    return ToolListResponse(
        data=[_tool_to_response(t) for t in tools],
        total=total,
        page=page,
        per_page=limit,
    )


@crud_router.get(
    "/{tool_id:int}",
    response_model=ToolResponse,
    summary="Get tool by ID",
)
async def get_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolResponse:
    result = await db.execute(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.tenant_id == current_user.tenant_id,
            Tool.deleted_at.is_(None),
        )
    )
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Tool {tool_id} not found",
        )
    return _tool_to_response(tool)


@crud_router.put(
    "/{tool_id:int}",
    response_model=ToolResponse,
    summary="Update tool",
)
async def update_tool(
    tool_id: int,
    data: ToolUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolResponse:
    result = await db.execute(
        select(Tool)
        .where(
            Tool.id == tool_id,
            Tool.tenant_id == current_user.tenant_id,
            Tool.deleted_at.is_(None),
        )
        .with_for_update()
    )
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Tool {tool_id} not found",
        )

    old_version = tool.version
    snapshot: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "id": tool.id,
        "name": tool.name,
        "description": tool.description,
        "tool_type": tool.tool_type,
        "status": tool.status,
        "code": tool.code,
        "endpoint_url": tool.endpoint_url,
        "parameters": tool.parameters,
        "metadata": tool.metadata_,
        "tags": tool.tags,
        "timeout_seconds": tool.timeout_seconds,
        "retry_policy": tool.retry_policy,
        "version": old_version,
    }
    version_record = ToolVersion(
        tool_id=tool.id,
        tenant_id=tool.tenant_id,
        version=old_version,
        snapshot=snapshot,
    )
    db.add(version_record)

    if data.name is not None:
        tool.name = data.name
    if data.description is not None:
        tool.description = data.description
    if data.code is not None:
        tool.code = data.code
    if data.endpoint_url is not None:
        tool.endpoint_url = data.endpoint_url
    if data.parameters is not None:
        tool.parameters = [p.model_dump() for p in data.parameters]
    if data.metadata is not None:
        tool.metadata_ = data.metadata
    if data.tags is not None:
        tool.tags = data.tags
    if data.status is not None:
        tool.status = data.status.value
    if data.timeout_seconds is not None:
        tool.timeout_seconds = data.timeout_seconds
    if data.retry_policy is not None:
        tool.retry_policy = data.retry_policy

    tool.version = old_version + 1
    tool.updated_at = datetime.now(timezone.utc)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "Tool %s version conflict for tenant %s",
            tool_id,
            current_user.tenant_id,
        )
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Tool was updated concurrently. Please retry.",
        ) from exc
    await db.refresh(tool)
    logger.info("Tool %s updated to version %s", tool_id, tool.version)
    return _tool_to_response(tool)


@crud_router.delete(
    "/{tool_id:int}",
    status_code=http_status.HTTP_200_OK,
    summary="Delete tool (soft delete)",
)
async def delete_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    result = await db.execute(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.tenant_id == current_user.tenant_id,
            Tool.deleted_at.is_(None),
        )
    )
    tool = result.scalar_one_or_none()
    if tool is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Tool {tool_id} not found",
        )
    tool.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Tool %s soft-deleted by user %s", tool_id, current_user.id)
    return {"detail": "Tool deleted"}
