from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.usage_models import UsageRecord


class UsageService:
    """
    Usage metering service for tracking resource consumption.
    Allows recording and querying usage per tenant and user.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record_usage(
        self,
        tenant_id: int,
        metric_type: str,
        value: float = 1.0,
        user_id: int | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Record a new usage event.
        """
        try:
            record = UsageRecord(
                tenant_id=tenant_id,
                user_id=user_id,
                metric_type=metric_type,
                value=value,
                metadata_json=metadata,
            )
            self.db.add(record)
            await self.db.commit()
            return True
        except Exception as e:
            logger.error(f"Error recording usage: {str(e)}")
            await self.db.rollback()
            return False

    async def get_monthly_usage(
        self,
        tenant_id: int,
        metric_type: str,
        month: int | None = None,
        year: int | None = None,
    ) -> float:
        """
        Get the total usage for a specific metric in a month.
        Defaults to the current month.
        """
        now = datetime.now(timezone.utc)
        target_month = month or now.month
        target_year = year or now.year

        start_date = datetime(target_year, target_month, 1)
        if target_month == 12:
            end_date = datetime(target_year + 1, 1, 1)
        else:
            end_date = datetime(target_year, target_month + 1, 1)

        try:
            query = select(func.sum(UsageRecord.value)).where(
                UsageRecord.tenant_id == tenant_id,
                UsageRecord.metric_type == metric_type,
                UsageRecord.timestamp >= start_date,
                UsageRecord.timestamp < end_date,
            )
            result = await self.db.execute(query)
            return result.scalar() or 0.0
        except Exception as e:
            logger.error(f"Error querying usage: {str(e)}")
            return 0.0

    async def check_quota(self, tenant_id: int, metric_type: str, limit: float) -> bool:
        """
        Check if the tenant has exceeded their quota for a metric.
        """
        current_usage = await self.get_monthly_usage(tenant_id, metric_type)
        return current_usage < limit
