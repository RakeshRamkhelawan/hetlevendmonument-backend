# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Workflow versioning sub-router (SP-API-003 Dag 2).

Routes:
    POST /api/v1/workflows/{workflow_id}/versions
    GET  /api/v1/workflows/{workflow_id}/versions
    GET  /api/v1/workflows/{workflow_id}/versions/{version_number}
    POST /api/v1/workflows/{workflow_id}/versions/{version_number}/rollback
    GET  /api/v1/workflows/{workflow_id}/compare

Security: JWT required, tenant isolated
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.workflow.dependencies import (
    get_db,
    require_scopes,
    OAuth2Scope,
    get_current_tenant_id,
    WorkflowVersioningService,
)
from src.core.auth.api_deps import get_current_user
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflow-versioning"])


# ============================================================================
# Shared sub-models (also used by workflow_versioning_router internals)
# ============================================================================


class WorkflowNode(BaseModel):
    """Workflow node definition."""

    id: str
    name: str
    type: str
    x: float = 0
    y: float = 0
    data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class WorkflowEdge(BaseModel):
    """Workflow edge/connection definition."""

    id: str
    source: str
    target: str
    type: str = "smoothstep"


class WorkflowDefinition(BaseModel):
    """Complete workflow definition."""

    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


# ============================================================================
# Request/Response Models
# ============================================================================


class SaveVersionRequest(BaseModel):
    """Request to save a new workflow version."""

    workflow_id: str = Field(..., description="Unique workflow identifier")
    name: str = Field(..., description="Workflow name")
    workflow: WorkflowDefinition = Field(..., description="Complete workflow definition")
    change_description: str = Field("", description="What changed in this version")
    tags: list[str] = Field(default_factory=list, description="Tags for categorizing version")


class WorkflowVersionInfo(BaseModel):
    """Information about a workflow version."""

    version_number: int = Field(..., description="Version number")
    name: str = Field(..., description="Workflow name")
    created_by: int = Field(..., description="User ID who created this version")
    created_at: str = Field(..., description="ISO timestamp when version was created")
    change_description: str | None = Field(None, description="Description of changes")
    tags: list[str] = Field(default_factory=list, description="Version tags")


class WorkflowVersionDetail(WorkflowVersionInfo):
    """Complete workflow version with full definition."""

    workflow_spec: dict[str, Any] = Field(..., description="Complete workflow specification")


class VersionHistoryResponse(BaseModel):
    """List of workflow versions."""

    workflow_id: str = Field(..., description="Workflow identifier")
    versions: list[WorkflowVersionInfo] = Field(..., description="List of versions")
    total_count: int = Field(..., description="Total number of versions")


class RollbackRequest(BaseModel):
    """Request to rollback to a previous version."""

    target_version: int = Field(..., description="Version number to rollback to")


class RollbackResponse(BaseModel):
    """Response from rollback operation."""

    success: bool = Field(..., description="Whether rollback was successful")
    message: str = Field(..., description="Status message")
    new_version_number: int | None = Field(None, description="New version created from rollback")
    workflow: WorkflowDefinition | None = Field(None, description="Restored workflow definition")


class VersionComparison(BaseModel):
    """Comparison between two versions."""

    version1: int = Field(..., description="First version number")
    version2: int = Field(..., description="Second version number")
    created_at_v1: str = Field(..., description="When v1 was created")
    created_at_v2: str = Field(..., description="When v2 was created")
    nodes_change: int = Field(..., description="Change in node count (positive = added)")
    edges_change: int = Field(..., description="Change in edge count (positive = added)")
    description_v1: str = Field("", description="v1 change description")
    description_v2: str = Field("", description="v2 change description")


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/{workflow_id}/versions", response_model=WorkflowVersionInfo, status_code=201)
async def save_workflow_version(
    workflow_id: str,
    request: SaveVersionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> WorkflowVersionInfo:
    """
    Save a new version/snapshot of a workflow.

    Security: JWT required, tenant isolated, WORKFLOWS_WRITE scope needed
    """
    logger.info(
        "Saving workflow version",
        extra={
            "tenant_id": tenant_id,
            "workflow_id": workflow_id,
            "user_id": current_user.id,
            "change": request.change_description[:50],
        },
    )

    try:
        version = await WorkflowVersioningService.save_version(
            db=db,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            name=request.name,
            workflow=request.workflow,  # type: ignore[arg-type]
            created_by=current_user.id,
            change_description=request.change_description,
            tags=request.tags,
        )

        await db.commit()

        logger.info(
            "Workflow version %s saved",
            version.version_number,
            extra={
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "version": version.version_number,
            },
        )

        return WorkflowVersionInfo(
            version_number=version.version_number,
            name=version.name,
            created_by=version.created_by,
            created_at=version.created_at.isoformat() if version.created_at else "",
            change_description=version.change_description or "",
            tags=version.tags or [],
        )

    except Exception as e:
        logger.error(
            "Failed to save version: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to save workflow version") from e


@router.get("/{workflow_id}/versions", response_model=VersionHistoryResponse)
async def get_version_history(
    workflow_id: str,
    limit: int = Query(10, ge=1, le=100, description="Max versions to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> VersionHistoryResponse:
    """
    Get version history for a workflow.

    Security: JWT required, tenant isolated, WORKFLOWS_READ scope needed
    """
    logger.info(
        "Fetching version history",
        extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "limit": limit},
    )

    try:
        versions = await WorkflowVersioningService.get_version_history(
            db=db,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            limit=limit,
        )

        return VersionHistoryResponse(
            workflow_id=workflow_id,
            versions=[
                WorkflowVersionInfo(
                    version_number=v.version_number,
                    name=v.name,
                    created_by=v.created_by,
                    created_at=v.created_at.isoformat() if v.created_at else "",
                    change_description=v.change_description or "",
                    tags=v.tags or [],
                )
                for v in versions
            ],
            total_count=len(versions),
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve version history: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve version history") from e


@router.get("/{workflow_id}/versions/{version_number}", response_model=WorkflowVersionDetail)
async def get_specific_version(
    workflow_id: str,
    version_number: int = Path(..., ge=1, description="Version number to retrieve"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> WorkflowVersionDetail:
    """
    Get a specific workflow version.

    Security: JWT required, tenant isolated, WORKFLOWS_READ scope needed
    """
    logger.info(
        "Fetching specific version",
        extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "version": version_number},
    )

    try:
        version = await WorkflowVersioningService.get_version(
            db=db,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            version_number=version_number,
        )

        if not version:
            raise HTTPException(
                status_code=404,
                detail="Version %s not found for workflow %s" % (version_number, workflow_id),
            )

        return WorkflowVersionDetail(
            version_number=version.version_number,
            name=version.name,
            created_by=version.created_by,
            created_at=version.created_at.isoformat() if version.created_at else "",
            change_description=version.change_description or "",
            tags=version.tags or [],
            workflow_spec=version.workflow_spec,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to retrieve version: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "version": version_number},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve version") from e


@router.post("/{workflow_id}/versions/{version_number}/rollback", response_model=RollbackResponse)
async def rollback_to_version(
    workflow_id: str,
    version_number: int = Path(..., ge=1, description="Version to rollback to"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),
) -> RollbackResponse:
    """
    Rollback workflow to a previous version.

    Security: JWT required, tenant isolated, WORKFLOWS_WRITE scope needed
    """
    logger.info(
        "Rolling back workflow",
        extra={
            "tenant_id": tenant_id,
            "workflow_id": workflow_id,
            "target_version": version_number,
            "user_id": current_user.id,
        },
    )

    try:
        new_version = await WorkflowVersioningService.rollback_to_version(
            db=db,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            target_version=version_number,
            rolled_back_by=current_user.id,
        )

        workflow_spec = new_version.workflow_spec
        workflow = WorkflowDefinition(
            nodes=[
                WorkflowNode(
                    id=n["id"],
                    name=n["name"],
                    type=n["type"],
                    x=n.get("x", 0),
                    y=n.get("y", 0),
                    data=n.get("data", {}),
                )
                for n in workflow_spec.get("nodes", [])
            ],
            edges=[
                WorkflowEdge(
                    id=e["id"],
                    source=e["source"],
                    target=e["target"],
                    type=e.get("type", "smoothstep"),
                )
                for e in workflow_spec.get("edges", [])
            ],
        )

        logger.info(
            "Rolled back to version %s",
            version_number,
            extra={
                "tenant_id": tenant_id,
                "workflow_id": workflow_id,
                "new_version": new_version.version_number,
            },
        )

        return RollbackResponse(
            success=True,
            message="Rolled back to version %s. New version: %s"
            % (version_number, new_version.version_number),
            new_version_number=new_version.version_number,
            workflow=workflow,
        )

    except ValueError as e:
        logger.warning(
            "Rollback validation error: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "version": version_number},
        )
        raise HTTPException(status_code=400, detail="Ongeldig verzoek.") from e
    except Exception as e:
        logger.error(
            "Rollback failed: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "version": version_number},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Rollback failed") from e


@router.get("/{workflow_id}/compare", response_model=VersionComparison)
async def compare_versions(
    workflow_id: str,
    v1: int = Query(..., ge=1, description="First version number"),
    v2: int = Query(..., ge=1, description="Second version number"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: int = Depends(get_current_tenant_id),
    _: int = Depends(require_scopes(OAuth2Scope.WORKFLOWS_READ)),
) -> VersionComparison:
    """
    Compare two workflow versions.

    Security: JWT required, tenant isolated, WORKFLOWS_READ scope needed
    """
    logger.info(
        "Comparing versions",
        extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "v1": v1, "v2": v2},
    )

    try:
        comparison = await WorkflowVersioningService.compare_versions(
            db=db,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            version1=v1,
            version2=v2,
        )
        return VersionComparison(**comparison)

    except ValueError as e:
        logger.warning(
            "Comparison validation error: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "v1": v1, "v2": v2},
        )
        raise HTTPException(status_code=400, detail="Ongeldig verzoek.") from e
    except Exception as e:
        logger.error(
            "Comparison failed: %s: %s",
            type(e).__name__,
            e,
            extra={"tenant_id": tenant_id, "workflow_id": workflow_id, "v1": v1, "v2": v2},
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Comparison failed") from e
