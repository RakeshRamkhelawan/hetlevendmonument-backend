# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow CRUD sub-router (SP-API-003).

Routes: POST /api/v1/workflows, GET /api/v1/workflows,
        GET /api/v1/workflows/stats, GET /api/v1/workflows/{workflow_id},
        PUT /api/v1/workflows/{workflow_id}, DELETE /api/v1/workflows/{workflow_id}
"""

import logging
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.workflow.dependencies import (
    C7Workflow as Workflow,
    get_db,
    OAuth2Scope,
    WorkflowService,
)
from src.core.auth.api_deps import require_scopes as _require_scopes
from src.core.exceptions import raise_not_found, raise_validation_error
from src.core.middleware.tenant_context import get_current_tenant_id as _get_current_tenant_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows-c7"])


WorkflowResponse = dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class WorkflowCreateRequest(BaseModel):
    """Request to create a new workflow."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    name: str = Field(..., description="Workflow name")
    description: str = Field("", description="Workflow description")
    workflow_type: str = Field("general", description="Workflow type/category")
    trigger_type: str = Field("manual", description="Trigger type (manual, scheduled, event)")
    spec: dict[str, Any] = Field(..., description="Workflow DAG specification")
    timeout: int = Field(3600, description="Timeout in seconds", ge=1, le=86400)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class WorkflowListItem(BaseModel):
    """Workflow list item."""

    workflow_id: str
    name: str
    description: str | None
    version: int
    is_active: bool
    created_at: str | None
    task_count: int


def _dt(dt: datetime | None) -> str | None:
    """Serialize datetime to ISO format."""
    return dt.isoformat() if dt else None


async def get_tenant() -> int:
    """Get tenant ID with error handling."""
    tenant_id = _get_current_tenant_id()
    if not tenant_id:
        raise_validation_error(
            "Tenant context required. Ensure you are authenticated with a valid JWT token containing tenant_id.",
            {"error": "MISSING_TENANT_CONTEXT"},
        )
    return tenant_id


@router.post("/", status_code=http_status.HTTP_201_CREATED)
async def create_workflow(
    request: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> WorkflowResponse:
    """Create a new workflow definition. Security: JWT required, tenant isolated."""
    service = WorkflowService(db)
    workflow = await service.create_workflow(
        tenant_id=tenant_id,
        user_id=user_id,
        workflow_id=request.workflow_id,
        name=request.name,
        description=request.description,
        workflow_type=request.workflow_type,
        trigger_type=request.trigger_type,
        spec=request.spec,
        timeout=request.timeout,
        metadata=request.metadata,
    )

    logger.info(
        "Workflow created",
        extra={
            "workflow_id": workflow.workflow_id,
            "version": workflow.version,
            "tenant_id": tenant_id,
            "created_by": workflow.owner_id,
        },
    )

    return {
        "workflow_id": workflow.workflow_id,
        "version": workflow.version,
        "status": "created",
        "message": "Workflow %s v%s created successfully" % (request.workflow_id, workflow.version),
    }


@router.get("/", response_model=list[WorkflowListItem])
async def list_workflows(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    _: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> list[WorkflowListItem]:
    """List workflows with pagination. Security: JWT required, tenant isolated."""
    service = WorkflowService(db)
    workflows = await service.list_workflows(tenant_id, limit, offset)

    return [
        WorkflowListItem(
            workflow_id=w.workflow_id,
            name=w.name,
            description=w.description,
            version=w.version,
            is_active=w.is_active,
            created_at=_dt(cast(datetime | None, w.created_at)),
            task_count=len(w.spec_json.get("tasks", [])),
        )
        for w in workflows
    ]


@router.get("/stats")
async def get_workflow_stats(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    _: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get workflow statistics for dashboard. Security: JWT required, tenant isolated."""
    total_query = select(Workflow).where(Workflow.tenant_id == tenant_id)
    total_result = await db.execute(total_query)
    total_workflows = len(total_result.scalars().all())

    active_query = select(Workflow).where(
        Workflow.tenant_id == tenant_id, Workflow.is_active.is_(True)
    )
    active_result = await db.execute(active_query)
    active_workflows = len(active_result.scalars().all())

    return {
        "total_workflows": total_workflows,
        "active_workflows": active_workflows,
        "inactive_workflows": total_workflows - active_workflows,
    }


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: str,
    version: int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> WorkflowResponse:
    """Get workflow definition by ID. Security: JWT required, tenant isolated."""
    query = select(Workflow).where(
        and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id)
    )

    if version:
        query = query.where(Workflow.version == version)
    else:
        query = query.order_by(Workflow.version.desc())

    result = await db.execute(query)
    workflow = result.scalars().first()

    if not workflow:
        raise_not_found("Workflow", workflow_id)

    return {
        "workflow_id": workflow.workflow_id,
        "version": workflow.version,
        "name": workflow.name,
        "description": workflow.description,
        "spec": workflow.spec_json,
        "is_active": workflow.is_active,
        "created_at": _dt(cast(datetime | None, workflow.created_at)),
        "updated_at": _dt(cast(datetime | None, workflow.created_at)),
        "status": "active" if workflow.is_active else "inactive",
    }


@router.put("/{workflow_id}", status_code=http_status.HTTP_200_OK)
async def update_workflow(
    workflow_id: str,
    request: WorkflowCreateRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> WorkflowResponse:
    """Update workflow (creates new version). Security: JWT required, tenant isolated."""
    query = (
        select(Workflow)
        .where(and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id))
        .order_by(Workflow.version.desc())
    )

    result = await db.execute(query)
    latest_workflow = result.scalars().first()

    if not latest_workflow:
        raise_not_found("Workflow", workflow_id)

    old_version = latest_workflow.version
    new_version = old_version + 1

    spec = request.spec
    nodes = spec.get("nodes", spec.get("tasks", []))
    edges = spec.get("edges", spec.get("dependencies", []))

    latest_workflow.name = request.name
    latest_workflow.description = request.description
    latest_workflow.workflow_type = request.workflow_type
    latest_workflow.trigger_type = request.trigger_type
    latest_workflow.version = new_version
    latest_workflow.nodes = nodes
    latest_workflow.edges = edges
    latest_workflow.variables = request.metadata
    latest_workflow.owner_id = user_id
    latest_workflow.is_active = True

    await db.commit()

    logger.info(
        "Workflow updated (new version)",
        extra={
            "workflow_id": workflow_id,
            "old_version": old_version,
            "new_version": new_version,
            "tenant_id": tenant_id,
            "updated_by": str(user_id),
        },
    )

    return {
        "workflow_id": latest_workflow.workflow_id,
        "version": new_version,
        "status": "updated",
        "message": "Workflow %s updated to v%s" % (workflow_id, new_version),
    }


@router.delete("/{workflow_id}", status_code=http_status.HTTP_200_OK)
async def delete_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    user_id: int = Depends(_require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Soft-delete workflow (set all versions to inactive)."""
    query = select(Workflow).where(
        and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id)
    )
    result = await db.execute(query)
    if not result.scalars().first():
        raise_not_found("Workflow", workflow_id)

    from sqlalchemy import update

    await db.execute(
        update(Workflow)
        .where(and_(Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id))
        .values(is_active=False)
    )

    await db.commit()

    logger.info(
        "Workflow deleted (soft)",
        extra={
            "workflow_id": workflow_id,
            "tenant_id": tenant_id,
            "deleted_by": str(user_id),
        },
    )

    return {
        "workflow_id": workflow_id,
        "status": "deleted",
        "message": "Workflow deleted successfully",
    }
