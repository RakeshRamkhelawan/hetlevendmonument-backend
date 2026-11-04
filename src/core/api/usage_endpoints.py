# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import get_current_user
from src.core.database.database import get_db
from src.core.models.rbac_models import User
from src.core.services.usage_service import UsageService

router = APIRouter(prefix="/usage", tags=["Usage"])


@router.get("/status")
async def get_usage_status(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get current usage statistics for the user.
    """
    usage_service = UsageService(db)

    # Define metrics to track
    metrics = ["workflow_run", "ai_token"]
    status: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    for metric in metrics:
        used = await usage_service.get_monthly_usage(current_user.tenant_id, metric)
        status[metric] = {
            "used": used,
            "limit": 50 if current_user.subscription_tier == "free" else 10000,  # Hardcoded for now
            "unit": "executions" if metric == "workflow_run" else "tokens",
        }

    return status


@router.post("/record")
async def record_manual_usage(
    metric_type: str,
    value: float = 1.0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Manually record usage (for internal testing or specific actions).
    """
    usage_service = UsageService(db)
    success = await usage_service.record_usage(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        metric_type=metric_type,
        value=value,
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to record usage")

    return {"status": "success"}
