from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.database.database import get_db
from src.core.workflow.models import C7Workflow as Workflow, C7WorkflowSnapshot as WorkflowSnapshot

router = APIRouter(tags=["Snapshots"])


@router.post("/snapshots/{workflow_id}", status_code=200)
async def store_snapshot(
    workflow_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: UserResponse = Depends(get_current_user),
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """
    Store a binary Yjs snapshot for a workflow.
    """
    tenant_id = user.tenant_id
    user_id = user.id

    # 1. Verify Workflow Exists & belongs to tenant
    stmt = select(Workflow).where(
        Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    workflow = result.scalars().first()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found or access denied")

    # 2. Read Binary Content
    content = await request.body()
    size_bytes = len(content)

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Empty snapshot content")

    # 3. Store Snapshot
    snapshot = WorkflowSnapshot(
        workflow_id=workflow_id,
        content=content,
        size_bytes=size_bytes,
        tenant_id=tenant_id,
        created_by=user_id,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)

    return {
        "id": snapshot.id,
        "workflow_id": snapshot.workflow_id,
        "size_bytes": snapshot.size_bytes,
        "created_at": snapshot.created_at,
    }


@router.get("/snapshots/{workflow_id}", status_code=200)
async def get_snapshot(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user: UserResponse = Depends(get_current_user),
) -> Response:
    """
    Retrieve the latest binary snapshot for a workflow.
    """
    tenant_id = user.tenant_id

    # 1. Verify Workflow Access
    stmt = select(Workflow).where(
        Workflow.workflow_id == workflow_id, Workflow.tenant_id == tenant_id
    )
    result = await db.execute(stmt)
    workflow = result.scalars().first()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # 2. Get Latest Snapshot
    # Order by created_at desc
    stmt_snap = (
        select(WorkflowSnapshot)
        .where(WorkflowSnapshot.workflow_id == workflow_id)
        .order_by(WorkflowSnapshot.created_at.desc())
    )

    result_snap = await db.execute(stmt_snap)
    snapshot = result_snap.scalars().first()

    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found for this workflow")

    return Response(content=snapshot.content, media_type="application/octet-stream")
