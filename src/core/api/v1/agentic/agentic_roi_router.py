"""Agentic ROI + health sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.v1.agentic.dependencies import ROICalculator
from src.core.auth.api_deps import get_current_user
from src.core.exceptions import AuthError
from src.core.middleware.tenant_context import require_tenant_id

agentic_roi_router = APIRouter()


@agentic_roi_router.get("/roi/supervisor/{supervisor}")
async def get_supervisor_roi(
    supervisor: str,
    hours: int = 168,
    _current_user: object = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get ROI metrics for a supervisor."""
    try:
        tenant_id_str = str(require_tenant_id())
        calculator = ROICalculator()
        days = max(1, hours // 24)
        metrics = await calculator.calculate_supervisor_roi(
            supervisor_id=supervisor, tenant_id=tenant_id_str, days=days
        )
        if metrics is None:
            raise HTTPException(status_code=404, detail="No ROI data found for supervisor")
        return {"supervisor": supervisor, "hours": hours, "metrics": metrics}
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@agentic_roi_router.get("/roi/dashboard")
async def get_roi_dashboard(
    period: str = "30d",
    _current_user: object = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get ROI dashboard data."""
    try:
        tenant_id_str = str(require_tenant_id())
        calculator = ROICalculator()
        dashboard = await calculator.get_dashboard_metrics(tenant_id=tenant_id_str)
        return {"period": period, "dashboard": dashboard}
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@agentic_roi_router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "agentic_api"}
