# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Tools execution + clone endpoints (ADR-033 Laag 1)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.tools.dependencies import get_current_user, get_db
from src.core.api.v1.tools.schemas import (
    ToolExecutionRequest,
    ToolExecutionResponse,
    ToolParameter,
    ToolResponse,
    ToolStatus,
    ToolType,
)
from src.core.models.rbac_models import User
from src.core.tool_broker.models import Tool

logger = logging.getLogger(__name__)

execution_router = APIRouter()


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


@execution_router.post(
    "/{tool_id}/execute",
    response_model=ToolExecutionResponse,
    summary="Execute tool",
)
async def execute_tool(
    tool_id: int,
    request: ToolExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolExecutionResponse:
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
    raise HTTPException(
        status_code=http_status.HTTP_501_NOT_IMPLEMENTED,
        detail="Tool execution engine not available for this tool type",
    )


@execution_router.post(
    "/{tool_id}/clone",
    response_model=ToolResponse,
    status_code=http_status.HTTP_201_CREATED,
    summary="Clone tool",
)
async def clone_tool(
    tool_id: int,
    new_name: str | None = Query(None, description="Name for the cloned tool"),
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
    source = result.scalar_one_or_none()
    if source is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Tool {tool_id} not found",
        )
    clone = Tool(
        tenant_id=current_user.tenant_id,
        name=new_name or f"{source.name}_copy",
        description=source.description,
        tool_type=source.tool_type,
        code=source.code,
        endpoint_url=source.endpoint_url,
        parameters=source.parameters,
        metadata_=source.metadata_,
        tags=source.tags,
        timeout_seconds=source.timeout_seconds,
        retry_policy=source.retry_policy,
        created_by=current_user.id,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    logger.info("Tool %s cloned to %s by user %s", tool_id, clone.id, current_user.id)
    return _tool_to_response(clone)


@execution_router.post(
    "/{tool_id}/test",
    response_model=ToolExecutionResponse,
    summary="Test tool (dry run)",
)
async def test_tool(
    tool_id: int,
    request: ToolExecutionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ToolExecutionResponse:
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
    return ToolExecutionResponse(
        success=True,
        result={"tool_type": tool.tool_type, "valid": True},
        error=None,
        execution_time_ms=0,
        logs=["dry-run: no side effects"],
    )
