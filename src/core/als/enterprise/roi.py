"""ROI Calculator for SanskritiSetu.

Calculates return on investment for Domain Packs and agent usage.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from src.core.exceptions import AuthError

logger = logging.getLogger(__name__)


class ROIMetrics(BaseModel):
    """Individual ROI measurement."""

    pack_id: str | None = None
    agent_id: str | None = None
    tenant_id: str
    execution_date: datetime
    time_saved_minutes: float = Field(ge=0)
    cost_saved_eur: float = Field(default=0.0, ge=0)
    manual_cost_avoided_eur: float = Field(default=0.0, ge=0)
    success: bool = True

    @validator("time_saved_minutes", "cost_saved_eur", "manual_cost_avoided_eur")
    def must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v


class ROICalculator:
    """Calculates ROI for Domain Packs and agent usage.

    Provides:
    - Per-pack ROI analysis
    - Per-supervisor ROI analysis
    - Platform-wide ROI dashboard
    - Time and cost savings calculations
    """

    # Default values for calculations
    DEFAULT_HOURLY_RATE_EUR = 50.0  # Average employee hourly cost
    DEFAULT_PLATFORM_COST_PER_EXECUTION = 0.10  # 10 cents per execution

    def __init__(
        self,
        hourly_rate_eur: float = DEFAULT_HOURLY_RATE_EUR,
        platform_cost_per_execution: float = DEFAULT_PLATFORM_COST_PER_EXECUTION,
    ) -> None:
        """Initialize ROI calculator.

        Args:
            hourly_rate_eur: Average hourly employee cost in EUR
            platform_cost_per_execution: Platform cost per execution
        """
        self.hourly_rate_eur = hourly_rate_eur
        self.platform_cost_per_execution = platform_cost_per_execution

    async def calculate_pack_roi(
        self, pack_id: str, tenant_id: str, days: int = 30
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Calculate ROI for a specific Domain Pack.

        Args:
            pack_id: Domain Pack identifier
            tenant_id: Tenant identifier
            days: Number of days to analyze

        Returns:
            ROI metrics or None if no data
        """
        if not tenant_id:
            raise AuthError("tenant_id is required for ROI calculation")

        # Get execution statistics
        stats = await self._get_pack_stats(pack_id, tenant_id, days)

        if not stats or stats["total_executions"] == 0:
            logger.warning(f"No data for pack {pack_id}")
            return None

        # Calculate metrics
        total_executions = stats["total_executions"]
        successful = stats["successful_executions"]
        time_saved_minutes = stats.get("total_time_saved_minutes", 0)
        estimated_value = stats.get("estimated_value_eur", 0)

        # Convert to hours
        time_saved_hours = time_saved_minutes / 60

        # Calculate cost savings
        manual_cost_saved = time_saved_hours * self.hourly_rate_eur
        platform_cost = total_executions * self.platform_cost_per_execution

        # Total value
        total_value = manual_cost_saved + estimated_value
        net_value = total_value - platform_cost

        # ROI percentage
        roi_percentage = self._calculate_roi_percentage(total_value, platform_cost)

        return {
            "pack_id": pack_id,
            "tenant_id": tenant_id,
            "period_days": days,
            "total_executions": total_executions,
            "successful_executions": successful,
            "success_rate": successful / total_executions if total_executions > 0 else 0,
            "total_time_saved_hours": round(time_saved_hours, 2),
            "total_time_saved_minutes": time_saved_minutes,
            "manual_cost_saved_eur": round(manual_cost_saved, 2),
            "platform_cost_eur": round(platform_cost, 2),
            "estimated_value_generated_eur": round(estimated_value, 2),
            "total_value_eur": round(total_value, 2),
            "net_value_eur": round(net_value, 2),
            "roi_percentage": round(roi_percentage, 2),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def calculate_supervisor_roi(
        self, supervisor_id: str, tenant_id: str, days: int = 30
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Calculate ROI for a supervisor's agents.

        Args:
            supervisor_id: Supervisor identifier
            tenant_id: Tenant identifier
            days: Number of days to analyze

        Returns:
            ROI metrics or None if no data
        """
        if not tenant_id:
            raise AuthError("tenant_id is required for ROI calculation")

        stats = await self._get_supervisor_stats(supervisor_id, tenant_id, days)

        if not stats or stats["total_tasks"] == 0:
            return None

        total_tasks = stats["total_tasks"]
        successful = stats["successful_tasks"]
        avg_time_ms = stats.get("avg_execution_time_ms", 0)
        manual_time_minutes = stats.get("manual_time_per_task_minutes", 30)

        # Calculate time saved per task
        automated_time_minutes = avg_time_ms / 1000 / 60
        time_saved_per_task = max(0, manual_time_minutes - automated_time_minutes)
        total_time_saved_hours = (time_saved_per_task * total_tasks) / 60

        # Calculate costs
        manual_cost = total_time_saved_hours * self.hourly_rate_eur
        platform_cost = total_tasks * self.platform_cost_per_execution
        net_value = manual_cost - platform_cost

        return {
            "supervisor_id": supervisor_id,
            "tenant_id": tenant_id,
            "period_days": days,
            "total_tasks": total_tasks,
            "successful_tasks": successful,
            "success_rate": successful / total_tasks if total_tasks > 0 else 0,
            "avg_execution_time_ms": avg_time_ms,
            "time_saved_per_task_minutes": round(time_saved_per_task, 2),
            "total_time_saved_hours": round(total_time_saved_hours, 2),
            "manual_cost_saved_eur": round(manual_cost, 2),
            "platform_cost_eur": round(platform_cost, 2),
            "net_value_eur": round(net_value, 2),
            "roi_percentage": round(self._calculate_roi_percentage(manual_cost, platform_cost), 2),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def calculate_platform_roi(self, tenant_id: str, days: int = 30) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Calculate overall platform ROI.

        Args:
            tenant_id: Tenant identifier
            days: Number of days to analyze

        Returns:
            Platform-wide ROI metrics
        """
        if not tenant_id:
            raise AuthError("tenant_id is required for ROI calculation")

        try:
            stats = await self._get_platform_stats(tenant_id, days)
        except Exception as e:
            logger.error(f"Failed to get platform stats: {e}")
            # Return fallback data on error
            stats = {}
        # Safe defaults if no data
        total_packs = stats.get("total_packs_executed", 0)
        total_agents = stats.get("total_agents_executed", 0)
        time_saved = stats.get("total_time_saved_hours", 0)
        operational_cost = stats.get("operational_cost_eur", 0)

        # Calculate value
        manual_cost_saved = time_saved * self.hourly_rate_eur
        platform_cost = (total_packs + total_agents) * self.platform_cost_per_execution
        total_cost = platform_cost + operational_cost

        net_value = manual_cost_saved - total_cost
        roi_percentage = self._calculate_roi_percentage(manual_cost_saved, total_cost)

        return {
            "tenant_id": tenant_id,
            "period_days": days,
            "total_packs_executed": total_packs,
            "total_agents_executed": total_agents,
            "total_executions": total_packs + total_agents,
            "total_time_saved_hours": round(time_saved, 2),
            "manual_cost_saved_eur": round(manual_cost_saved, 2),
            "platform_cost_eur": round(platform_cost, 2),
            "operational_cost_eur": round(operational_cost, 2),
            "total_cost_eur": round(total_cost, 2),
            "net_value_eur": round(net_value, 2),
            "roi_percentage": round(roi_percentage, 2),
            "payback_period_months": self._calculate_payback_period(total_cost, manual_cost_saved),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_dashboard_metrics(self, tenant_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get dashboard-ready ROI metrics.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Formatted dashboard data
        """
        if not tenant_id:
            raise AuthError("tenant_id is required")

        # Get various metrics
        platform_roi = await self.calculate_platform_roi(tenant_id, days=30)

        # Get top performing packs (mocked for now)
        top_packs = await self._get_top_packs(tenant_id, limit=5)

        # Calculate monthly trend
        monthly_trend = await self._get_monthly_trend(tenant_id, months=6)

        # Efficiency metrics
        efficiency = {
            "avg_execution_time_ms": platform_roi.get("avg_execution_time_ms", 0),
            "success_rate": platform_roi.get("success_rate", 0),
            "automated_percentage": 95.0,  # Placeholder
        }

        return {
            "overview": {
                "total_value_generated_eur": platform_roi.get("net_value_eur", 0),
                "total_time_saved_hours": platform_roi.get("total_time_saved_hours", 0),
                "roi_percentage": platform_roi.get("roi_percentage", 0),
                "executions_this_month": platform_roi.get("total_executions", 0),
            },
            "top_performing_packs": top_packs,
            "monthly_trend": monthly_trend,
            "efficiency_metrics": efficiency,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _calculate_time_saved(
        self, manual_time_minutes: float, automated_time_minutes: float, executions: int
    ) -> float:
        """Calculate total time saved.

        Args:
            manual_time_minutes: Time for manual execution
            automated_time_minutes: Time for automated execution
            executions: Number of executions

        Returns:
            Total time saved in minutes
        """
        saved_per_execution = max(0, manual_time_minutes - automated_time_minutes)
        return saved_per_execution * executions

    def _calculate_roi_percentage(self, gain: float, cost: float) -> float:
        """Calculate ROI percentage.

        Args:
            gain: Value gained
            cost: Cost invested

        Returns:
            ROI percentage (capped at 999.99 for JSON serialization)
        """
        if cost == 0:
            # Return capped value instead of infinity for JSON serialization
            return 999.99 if gain > 0 else 0.0

        roi = ((gain - cost) / cost) * 100
        # Cap at 999.99% to ensure JSON serialization works
        return min(roi, 999.99)

    def _calculate_payback_period(
        self, initial_cost: float, monthly_savings: float
    ) -> float | None:
        """Calculate payback period in months.

        Args:
            initial_cost: Initial investment
            monthly_savings: Monthly savings

        Returns:
            Payback period in months or None if no savings
        """
        if monthly_savings <= 0:
            return None
        return initial_cost / monthly_savings

    # Database query methods (placeholders)

    async def _get_pack_stats(
        self, pack_id: str, tenant_id: str, days: int
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get pack execution statistics from database."""
        # Placeholder - implement with actual DB query
        # Query would filter by pack_id, tenant_id, and date range
        logger.debug(f"Getting stats for pack {pack_id}")
        return {
            "total_executions": 10,
            "successful_executions": 9,
            "total_time_saved_minutes": 900,
            "estimated_value_eur": 5000,
        }

    async def _get_supervisor_stats(
        self, supervisor_id: str, tenant_id: str, days: int
    ) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get supervisor statistics from database."""
        logger.debug(f"Getting stats for supervisor {supervisor_id}")
        return {
            "total_tasks": 100,
            "successful_tasks": 95,
            "avg_execution_time_ms": 500,
            "manual_time_per_task_minutes": 30,
        }

    async def _get_platform_stats(self, tenant_id: str, days: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get platform-wide statistics from database."""
        logger.debug(f"Getting platform stats for {tenant_id}")
        return {
            "total_packs_executed": 50,
            "total_agents_executed": 200,
            "total_time_saved_hours": 500,
            "operational_cost_eur": 1000,
            "avg_execution_time_ms": 450,
        }

    async def _get_top_packs(self, tenant_id: str, limit: int = 5) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get top performing packs."""
        # Placeholder
        return [
            {"pack_id": "finance.monthly_close", "roi_percentage": 450},
            {"pack_id": "hr.onboarding", "roi_percentage": 320},
        ][:limit]

    async def _get_monthly_trend(self, tenant_id: str, months: int = 6) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get monthly ROI trend."""
        # Placeholder - would query monthly aggregates
        trend: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i in range(months):
            month = datetime.now(timezone.utc) - timedelta(days=30 * i)
            trend.append(
                {
                    "month": month.strftime("%Y-%m"),
                    "executions": 100 - i * 5,
                    "value_eur": 5000 - i * 200,
                }
            )
        return list(reversed(trend))
