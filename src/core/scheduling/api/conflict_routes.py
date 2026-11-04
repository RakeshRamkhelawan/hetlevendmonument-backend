"""
API endpoints for conflict resolution.

Provides endpoints for viewing and resolving calendar sync conflicts.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.scheduling.conflicts.resolution_service import ConflictResolutionService
from src.core.scheduling.schemas import (
    ConflictItem,
    ConflictListResponse,
    ConflictResolutionRequest,
    ConflictResolutionResponse,
    ConflictSummaryResponse,
)
from src.core.scheduling.webhooks.repository import SyncConflictRepository
from src.core.security.security_manager import ThreatLevel
from src.core.governance.services.audit_service import AuditService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scheduling/conflicts",
    tags=["Conflict Resolution"],
)


def get_conflict_service(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> ConflictResolutionService:
    """Dependency to get conflict resolution service."""
    return ConflictResolutionService(db, current_user.tenant_id)


def get_conflict_repo(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> SyncConflictRepository:
    """Dependency to get conflict repository."""
    return SyncConflictRepository(db, current_user.tenant_id)


# ========================================================================
# List Conflicts
# ========================================================================


@router.get(
    "",
    response_model=ConflictListResponse,
    summary="List calendar sync conflicts",
)
async def list_conflicts(
    integration_id: str | None = Query(None, description="Filter by integration"),
    status: str | None = Query("pending", description="Filter by status"),
    severity: str | None = Query(None, description="Filter by severity"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of items to return"),
    current_user: UserResponse = Depends(get_current_user),
    repo: SyncConflictRepository = Depends(get_conflict_repo),
) -> ConflictListResponse:
    """
    List calendar sync conflicts for the current user.

    Returns conflicts between local and external calendar events
    that require resolution.
    """
    # Get conflicts
    if status == "pending":
        conflicts = await repo.list_pending(integration_id)
    else:
        conflicts = await repo.list_by_integration(integration_id, status)  # type: ignore[arg-type]  # integration_id may be None, handled by repo

    # Filter by severity if specified
    if severity:
        conflicts = [c for c in conflicts if c.severity == severity]

    # Calculate total before pagination
    total = len(conflicts)

    # Apply pagination
    conflicts = conflicts[skip : skip + limit]

    # Convert to response model
    conflict_items: list[ConflictItem] = []
    for conflict in conflicts:
        conflict_items.append(
            ConflictItem(
                id=conflict.id,
                integration_id=conflict.integration_id,
                local_event_id=conflict.local_event_id,
                external_event_id=conflict.external_event_id,
                conflict_type=conflict.conflict_type,
                severity=conflict.severity,
                local_snapshot=conflict.local_snapshot,
                external_snapshot=conflict.external_snapshot,
                resolution_status=conflict.resolution_status,
                created_at=conflict.created_at,
            )
        )

    return ConflictListResponse(
        conflicts=conflict_items,
        total=total,
    )


# ========================================================================
# Get Conflict Summary
# ========================================================================


@router.get(
    "/summary",
    response_model=ConflictSummaryResponse,
    summary="Get conflict summary statistics",
)
async def get_conflict_summary(
    integration_id: str | None = Query(None, description="Filter by integration"),
    current_user: UserResponse = Depends(get_current_user),
    service: ConflictResolutionService = Depends(get_conflict_service),
) -> ConflictSummaryResponse:
    """
    Get summary statistics about conflicts.

    Returns counts by severity and type for dashboard display.
    """
    summary = await service.get_conflict_summary(integration_id)

    return ConflictSummaryResponse(
        total_pending=summary["total_pending"],
        by_severity=summary["by_severity"],
        by_type=summary["by_type"],
    )


# ========================================================================
# Resolve Conflict
# ========================================================================


@router.post(
    "/{conflict_id}/resolve",
    response_model=ConflictResolutionResponse,
    summary="Resolve a conflict",
)
async def resolve_conflict(
    conflict_id: str,
    data: ConflictResolutionRequest,
    current_user: UserResponse = Depends(get_current_user),
    service: ConflictResolutionService = Depends(get_conflict_service),
    db: AsyncSession = Depends(get_db),
) -> ConflictResolutionResponse:
    """
    Resolve a calendar sync conflict.

    Available strategies:
    - `keep_local`: Keep local event, discard external changes
    - `keep_external`: Overwrite local with external data
    - `merge`: Combine non-conflicting fields from both
    - `auto`: Automatically choose based on conflict type
    """
    result = await service.resolve_conflict(
        conflict_id=conflict_id,
        strategy_name=data.strategy,
        resolved_by=str(current_user.id),
        custom_data=data.custom_data,
    )

    # Audit log the resolution
    if result.success:
        await AuditService.log_event(
            db=db,
            event_type="CONFLICT_RESOLVED",
            severity=ThreatLevel.LOW,
            source_ip="internal",
            endpoint=f"/api/v1/scheduling/conflicts/{conflict_id}/resolve",
            description=f"Conflict resolved using strategy: {result.strategy}",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="UPDATE",
            resource=f"conflict:{conflict_id}",
            metadata={
                "strategy": result.strategy,
                "action_taken": result.action_taken,
            },
        )
    else:
        await AuditService.log_event(
            db=db,
            event_type="CONFLICT_RESOLUTION_FAILED",
            severity=ThreatLevel.MEDIUM,
            source_ip="internal",
            endpoint=f"/api/v1/scheduling/conflicts/{conflict_id}/resolve",
            description=f"Conflict resolution failed: {result.error_message}",
            user_id=current_user.id,
            tenant_id=current_user.tenant_id,
            action="UPDATE",
            resource=f"conflict:{conflict_id}",
        )

    if result.error_message and not result.success:
        # Determine appropriate status code based on error message
        if "Conflict not found" in result.error_message:
            status_code = status.HTTP_404_NOT_FOUND
        elif "Conflict already resolved" in result.error_message:
            status_code = status.HTTP_409_CONFLICT
        elif "Unknown strategy" in result.error_message:
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_400_BAD_REQUEST

        raise HTTPException(
            status_code=status_code,
            detail=result.error_message,
        )

    return ConflictResolutionResponse(
        success=result.success,
        conflict_id=conflict_id,
        strategy=result.strategy,
        action_taken=result.action_taken,
        error_message=result.error_message,
    )


# ========================================================================
# Auto-Resolve Conflicts
# ========================================================================


@router.post(
    "/auto-resolve",
    response_model=dict,
    summary="Auto-resolve low-severity conflicts",
)
async def auto_resolve_conflicts(
    integration_id: str | None = Query(None, description="Limit to integration"),
    current_user: UserResponse = Depends(get_current_user),
    service: ConflictResolutionService = Depends(get_conflict_service),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Automatically resolve all low-severity conflicts.

    This endpoint should be called periodically (e.g., by a scheduled job)
    or manually by an admin.
    """
    result = await service.auto_resolve_conflicts(integration_id)

    return {
        "status": "completed",
        "total_processed": result["total"],
        "resolved": result["resolved"],
        "failed": result["failed"],
        "skipped": result["skipped"],
    }


# ========================================================================
# Get Single Conflict
# ========================================================================


@router.get(
    "/{conflict_id}",
    response_model=dict,
    summary="Get conflict details",
)
async def get_conflict(
    conflict_id: str,
    current_user: UserResponse = Depends(get_current_user),
    repo: SyncConflictRepository = Depends(get_conflict_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get detailed information about a specific conflict."""
    conflict = await repo.get_by_id(conflict_id)

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict not found: {conflict_id}",
        )

    return {
        "id": conflict.id,
        "integration_id": conflict.integration_id,
        "local_event_id": conflict.local_event_id,
        "external_event_id": conflict.external_event_id,
        "conflict_type": conflict.conflict_type,
        "severity": conflict.severity,
        "local_snapshot": conflict.local_snapshot,
        "external_snapshot": conflict.external_snapshot,
        "resolution_status": conflict.resolution_status,
        "resolution_strategy": conflict.resolution_strategy,
        "resolved_by": conflict.resolved_by,
        "resolved_at": conflict.resolved_at,
        "created_at": conflict.created_at,
    }


# ========================================================================
# Ignore Conflict
# ========================================================================


@router.post(
    "/{conflict_id}/ignore",
    response_model=dict,
    summary="Ignore a conflict",
)
async def ignore_conflict(
    conflict_id: str,
    current_user: UserResponse = Depends(get_current_user),
    repo: SyncConflictRepository = Depends(get_conflict_repo),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Mark a conflict as ignored.

    This keeps both versions as-is and prevents future auto-detection
    of this specific conflict.
    """
    conflict = await repo.get_by_id(conflict_id)

    if not conflict:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict not found: {conflict_id}",
        )

    if conflict.resolution_status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Conflict already resolved: {conflict.resolution_status}",
        )

    # Mark as ignored (manual resolution with ignore strategy)
    await repo.mark_resolved(
        conflict_id=conflict_id,
        strategy="ignore",
        resolved_by=str(current_user.id),
    )

    return {
        "success": True,
        "conflict_id": conflict_id,
        "action": "ignored",
    }
