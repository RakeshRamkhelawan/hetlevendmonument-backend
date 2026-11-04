"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
Sync API - YJS Document Snapshot Endpoints

Provides endpoints for the Hocuspocus sync-server to:
- Load document snapshots
- Save document snapshots
- Manage YJS document state
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.core.auth.api_deps import UserResponse, get_current_user

# Import health endpoints
from . import health
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflows", tags=["sync"])

# Include health endpoints
router.include_router(health.router, tags=["sync-health"])


@router.get("/{workflow_id}/snapshot")
async def get_workflow_snapshot(
    workflow_id: str,
    request: Request,
) -> Response:
    """
    Get YJS document snapshot for a workflow.

    Called by Hocuspocus sync-server when loading a document.
    Returns binary YJS update data.
    """
    try:
        # TODO: Implement actual snapshot retrieval from database
        # For now, return empty (new document will be created)

        # Example implementation:
        # result = await db.execute(
        #     select(WorkflowSnapshot)
        #     .where(WorkflowSnapshot.workflow_id == workflow_id)
        #     .order_by(WorkflowSnapshot.created_at.desc())
        # )
        # snapshot = result.scalar_one_or_none()
        #
        # if snapshot:
        #     return Response(
        #         content=snapshot.data,
        #         media_type="application/octet-stream"
        #     )

        # Return empty response (Hocuspocus will create new document)
        return Response(
            content=b"",
            media_type="application/octet-stream",
            status_code=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.error("get_workflow_snapshot mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load snapshot",
        )


@router.post("/{workflow_id}/snapshot")
async def save_workflow_snapshot(
    workflow_id: str,
    request: Request,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Save YJS document snapshot for a workflow.

    Called by Hocuspocus sync-server when saving a document.
    Accepts binary YJS update data.
    """
    try:
        # Read binary data from request body
        data = await request.body()

        # TODO: Implement actual snapshot storage
        # For now, just log the save operation

        # Example implementation:
        # snapshot = WorkflowSnapshot(
        #     workflow_id=workflow_id,
        #     data=data,
        #     created_at=datetime.now(timezone.utc)
        # )
        # db.add(snapshot)
        # await db.commit()

        return {"status": "saved", "workflow_id": workflow_id, "bytes": len(data)}

    except Exception as e:
        logger.error("save_workflow_snapshot mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save snapshot",
        )


@router.get("/{workflow_id}/awareness")
async def get_workflow_awareness(
    workflow_id: str,
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get awareness state for a workflow (active users, cursors, etc.)

    This is used by the frontend to show collaborative presence.
    """
    # TODO: Implement awareness state tracking
    # This would typically be stored in Redis for real-time access

    return {
        "workflow_id": workflow_id,
        "users": [],  # List of active users
        "cursors": [],  # Cursor positions
    }
