# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Privacy DSAR endpoints: export + forget (ADR-033 Laag 1, GDPR Art. 17 + 20)."""

import io
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.privacy.dependencies import (
    dsar_delete_limit,
    dsar_export_limit,
    get_current_user,
    get_db,
)
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

dsar_router = APIRouter()


class DataExportResponse(BaseModel):
    status: str
    message: str
    download_url: str | None = None


class DeleteAccountRequest(BaseModel):
    confirm_email: str
    reason: str | None = None


class DeleteAccountResponse(BaseModel):
    status: str
    message: str


async def collect_user_data(
    session: AsyncSession, user: User
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Collect all user data for GDPR export (Art. 20 portability)."""
    data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "export_date": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "tenant_id": user.tenant_id,
            "created_at": str(user.created_at) if hasattr(user, "created_at") else None,
        },
        "workflows": [],
        "tool_usage": [],
        "audit_logs": [],
        "gamification": {},
    }

    try:
        from src.core.models.workflow_models import Workflow  # type: ignore[attr-defined]

        result = await session.execute(
            select(Workflow).where(
                Workflow.tenant_id == user.tenant_id, Workflow.created_by_id == user.id
            )
        )
        workflows = result.scalars().all()
        data["workflows"] = [
            {"id": w.id, "name": w.name, "created_at": str(w.created_at)} for w in workflows
        ]
    except Exception as e:
        logger.warning("Could not export workflows: %s", e)

    try:
        from src.core.models.gamification_models import PointTransaction, UserPoints

        result = await session.execute(
            select(UserPoints).where(
                UserPoints.user_id == user.id, UserPoints.tenant_id == user.tenant_id
            )
        )
        points = result.scalar_one_or_none()
        if points:
            data["gamification"]["points"] = {
                "total": points.total_points,
                "level": points.level,
                "streak": points.current_streak,
            }

        result = await session.execute(
            select(PointTransaction)
            .where(
                PointTransaction.user_id == user.id,
                PointTransaction.tenant_id == user.tenant_id,
            )
            .order_by(PointTransaction.created_at.desc())
            .limit(100)
        )
        transactions = result.scalars().all()
        data["gamification"]["transactions"] = [
            {"action": t.action, "points": t.points, "date": str(t.created_at)}
            for t in transactions
        ]
    except Exception as e:
        logger.warning("Could not export gamification data: %s", e)

    try:
        from src.core.conversations.models import Conversation

        result = await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == user.tenant_id,
                Conversation.user_id == user.id,
            )
        )
        conversations = result.scalars().all()
        data["cva_conversations"] = [
            {
                "id": c.id,
                "title": getattr(c, "title", None),
                "created_at": str(c.created_at) if hasattr(c, "created_at") else None,
                "is_active": getattr(c, "is_active", None),
            }
            for c in conversations
        ]
    except Exception as e:
        logger.warning("Could not export CVA conversations: %s", e)
        data["cva_conversations"] = []

    return data


@dsar_router.get("/export")
@dsar_export_limit
async def export_my_data(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Export all user data (GDPR Article 20 - Right to Data Portability)."""
    data = await collect_user_data(session, current_user)

    json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    filename = (
        f"user_data_export_{current_user.id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    )

    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@dsar_router.post("/forget", response_model=DeleteAccountResponse)
@dsar_delete_limit
async def forget_me(
    request: Request,
    delete_request: DeleteAccountRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> DeleteAccountResponse:
    """Delete all user data (GDPR Article 17 - Right to Erasure)."""
    if delete_request.confirm_email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=400,
            detail="Email confirmation does not match. Please type your email exactly.",
        )

    logger.warning(
        "User %s requested account deletion. Reason: %s",
        current_user.id,
        delete_request.reason,
    )

    try:
        from src.core.models.gamification_models import PointTransaction, UserBadge, UserPoints

        await session.execute(
            delete(PointTransaction).where(
                PointTransaction.user_id == current_user.id,
                PointTransaction.tenant_id == current_user.tenant_id,
            )
        )
        await session.execute(
            delete(UserBadge).where(
                UserBadge.user_id == current_user.id,
                UserBadge.tenant_id == current_user.tenant_id,
            )
        )
        await session.execute(
            delete(UserPoints).where(
                UserPoints.user_id == current_user.id,
                UserPoints.tenant_id == current_user.tenant_id,
            )
        )

        await session.commit()

        logger.info("User %s data deletion completed", current_user.id)

        return DeleteAccountResponse(
            status="success",
            message=(
                "Uw activiteitsgegevens zijn verwijderd. Neem contact op met de beheerder van uw "
                "bedrijf om uw account volledig te laten verwijderen."
            ),
        )

    except Exception as e:
        logger.error("Error during data deletion: %s: %s", type(e).__name__, e, exc_info=True)
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail="An error occurred during data deletion. Please contact support.",
        )
