"""Dashboard domain dependencies (ADR-033 Laag 1)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.database.database import get_db as get_db  # noqa: F401


class DashboardService:
    """Service for Dashboard endpoints. Real queries replace stubs in a future sprint."""

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def get_daily_summary(self) -> dict[str, object]:
        return {
            "tasksCompleted": 0,
            "valueGenerated": 0,
            "topAgent": "N/B",
            "successRate": 0.0,
        }


def get_dashboard_service(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> DashboardService:
    return DashboardService(db=db, tenant_id=current_user.tenant_id)
