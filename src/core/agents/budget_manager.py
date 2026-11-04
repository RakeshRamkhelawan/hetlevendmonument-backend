"""
Token & Cost Budget Manager - Usage Tracking and Limits

Provides:
- Per-tenant and per-agent budget tracking
- Token usage limits (hourly, daily, per-task)
- Cost tracking in USD
- Redis-backed counters for real-time tracking
- Alert thresholds (80% warning, 100% block)
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SubscriptionTier(str, enum.Enum):
    """Subscription tiers with different budget defaults."""

    FREE = "free"
    STANDARD = "standard"
    ENTERPRISE = "enterprise"


@dataclass
class BudgetConfig:
    """Budget configuration for a tenant."""

    max_tokens_per_hour: int = 10000
    max_tokens_per_day: int = 100000
    max_cost_per_hour: Decimal = Decimal("1.00")
    max_cost_per_day: Decimal = Decimal("10.00")
    max_tokens_per_task: int = 10000
    alert_threshold: float = 0.8  # Alert at 80% usage

    @classmethod
    def for_tier(cls, tier: SubscriptionTier) -> BudgetConfig:
        """Get default config for subscription tier."""
        configs = {
            SubscriptionTier.FREE: cls(
                max_tokens_per_hour=1000,
                max_tokens_per_day=10000,
                max_cost_per_hour=Decimal("0.10"),
                max_cost_per_day=Decimal("1.00"),
                max_tokens_per_task=5000,
            ),
            SubscriptionTier.STANDARD: cls(
                max_tokens_per_hour=10000,
                max_tokens_per_day=100000,
                max_cost_per_hour=Decimal("1.00"),
                max_cost_per_day=Decimal("10.00"),
                max_tokens_per_task=10000,
            ),
            SubscriptionTier.ENTERPRISE: cls(
                max_tokens_per_hour=100000,
                max_tokens_per_day=1000000,
                max_cost_per_hour=Decimal("10.00"),
                max_cost_per_day=Decimal("100.00"),
                max_tokens_per_task=50000,
            ),
        }
        return configs.get(tier, cls())


@dataclass
class BudgetCheckResult:
    """Result of budget check."""

    allowed: bool
    remaining_tokens: int
    remaining_cost: Decimal
    current_usage_tokens: int
    current_usage_cost: Decimal
    reason: str | None = None
    alert_triggered: bool = False


class BudgetUsage(Base):  # type: ignore[misc]
    """Database model for budget usage history."""

    __tablename__ = "budget_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Usage metrics
    tokens_used: Mapped[int | None] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), default=0)

    # Time period (hourly buckets)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Model used (for cost calculation)
    model_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Metadata
    task_count: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("idx_budget_usage_tenant_period", "tenant_id", "period_start"),
        Index("idx_budget_usage_agent", "tenant_id", "agent_id", "period_start"),
    )


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""

    def __init__(self, message: str, remaining_tokens: int, remaining_cost: Decimal) -> None:
        self.remaining_tokens = remaining_tokens
        self.remaining_cost = remaining_cost
        super().__init__(message)


class BudgetManager:
    """
    Manager for token and cost budgets.

    Tracks usage per tenant and agent, enforces limits, and emits alerts.
    Uses Redis for real-time counters with automatic TTL-based reset.
    """

    def __init__(
        self,
        session: AsyncSession,
        redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        default_config: BudgetConfig | None = None,
    ) -> None:
        """
        Initialize budget manager.

        Args:
            session: Database session
            redis_client: Redis client for real-time counters (optional)
            default_config: Default budget config
        """
        self._session = session
        self._redis = redis_client
        self._default_config = default_config or BudgetConfig()

    async def check_budget(
        self,
        tenant_id: int,
        agent_id: str,
        estimated_tokens: int,
        config: BudgetConfig | None = None,
    ) -> BudgetCheckResult:
        """
        Check if a request is within budget.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            estimated_tokens: Estimated tokens for this request
            config: Budget config (uses default if not provided)

        Returns:
            BudgetCheckResult with allowance decision
        """
        cfg = config or self._default_config

        # Get current usage
        usage = await self._get_current_usage(tenant_id, agent_id)

        # Calculate remaining
        remaining_tokens = cfg.max_tokens_per_hour - usage["tokens_hour"]
        remaining_cost = cfg.max_cost_per_hour - Decimal(str(usage["cost_hour"]))

        # Check per-task limit
        if estimated_tokens > cfg.max_tokens_per_task:
            return BudgetCheckResult(
                allowed=False,
                remaining_tokens=remaining_tokens,
                remaining_cost=remaining_cost,
                current_usage_tokens=usage["tokens_hour"],
                current_usage_cost=Decimal(str(usage["cost_hour"])),
                reason=f"Per-task token limit ({cfg.max_tokens_per_task}) exceeded",
            )

        # Check if request would exceed budget
        if usage["tokens_hour"] + estimated_tokens > cfg.max_tokens_per_hour:
            return BudgetCheckResult(
                allowed=False,
                remaining_tokens=remaining_tokens,
                remaining_cost=remaining_cost,
                current_usage_tokens=usage["tokens_hour"],
                current_usage_cost=Decimal(str(usage["cost_hour"])),
                reason="Hourly token limit exceeded",
            )

        # Check alert threshold
        alert_triggered = False
        if cfg.max_tokens_per_hour > 0:
            usage_ratio = usage["tokens_hour"] / cfg.max_tokens_per_hour
            if usage_ratio >= cfg.alert_threshold:
                alert_triggered = True
                logger.warning(
                    f"Budget alert: Tenant {tenant_id} at {usage_ratio:.1%} of hourly token limit"
                )

        return BudgetCheckResult(
            allowed=True,
            remaining_tokens=remaining_tokens - estimated_tokens,
            remaining_cost=remaining_cost,
            current_usage_tokens=usage["tokens_hour"],
            current_usage_cost=Decimal(str(usage["cost_hour"])),
            alert_triggered=alert_triggered,
        )

    async def record_usage(
        self,
        tenant_id: int,
        agent_id: str,
        tokens_used: int,
        cost_usd: Decimal,
        model_name: str | None = None,
    ) -> None:
        """
        Record token and cost usage.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            tokens_used: Actual tokens used
            cost_usd: Cost in USD
            model_name: Model used
        """
        now = datetime.now(timezone.utc)
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        # Create or update usage record
        usage = BudgetUsage(
            tenant_id=tenant_id,
            agent_id=agent_id,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            period_start=hour_start,
            period_end=hour_end,
            model_name=model_name,
            task_count=1,
        )

        self._session.add(usage)
        await self._session.commit()

        # Update Redis counters if available
        if self._redis:
            await self._update_redis_counters(tenant_id, agent_id, tokens_used, cost_usd)

        logger.debug(
            f"Recorded usage: tenant={tenant_id}, agent={agent_id}, "
            f"tokens={tokens_used}, cost=${cost_usd}"
        )

    async def get_usage_report(
        self,
        tenant_id: int,
        period_hours: int = 24,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Get usage report for a tenant.

        Args:
            tenant_id: Tenant ID
            period_hours: Report period in hours

        Returns:
            Usage report dictionary
        """
        from sqlalchemy import func, select

        since = datetime.now(timezone.utc) - timedelta(hours=period_hours)

        result = await self._session.execute(
            select(
                BudgetUsage.agent_id,
                func.sum(BudgetUsage.tokens_used).label("total_tokens"),
                func.sum(BudgetUsage.cost_usd).label("total_cost"),
                func.sum(BudgetUsage.task_count).label("total_tasks"),
            )
            .where(BudgetUsage.tenant_id == tenant_id)
            .where(BudgetUsage.period_start >= since)
            .group_by(BudgetUsage.agent_id)
        )

        agent_breakdown: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        total_tokens = 0
        total_cost = Decimal("0")
        total_tasks = 0

        for row in result.all():
            agent_breakdown.append(
                {
                    "agent_id": row.agent_id,
                    "tokens": row.total_tokens or 0,
                    "cost_usd": float(row.total_cost or 0),
                    "tasks": row.total_tasks or 0,
                }
            )
            total_tokens += row.total_tokens or 0
            total_cost += Decimal(str(row.total_cost or 0))
            total_tasks += row.total_tasks or 0

        return {
            "tenant_id": tenant_id,
            "period_hours": period_hours,
            "total_tokens": total_tokens,
            "total_cost_usd": float(total_cost),
            "total_tasks": total_tasks,
            "agent_breakdown": agent_breakdown,
        }

    async def reset_budget(self, tenant_id: int) -> bool:
        """
        Reset budget counters (admin only).

        Args:
            tenant_id: Tenant ID

        Returns:
            True if reset successful
        """
        # Clear Redis counters if available
        if self._redis:
            keys = [
                f"budget:{tenant_id}:tokens:hour",
                f"budget:{tenant_id}:tokens:day",
                f"budget:{tenant_id}:cost:hour",
                f"budget:{tenant_id}:cost:day",
            ]
            for key in keys:
                await self._redis.delete(key)

        logger.info(f"Budget reset for tenant {tenant_id}")
        return True

    async def _get_current_usage(self, tenant_id: int, agent_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current usage from database or Redis."""
        from sqlalchemy import func, select

        hour_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

        # Query database for current hour usage
        result = await self._session.execute(
            select(
                func.sum(BudgetUsage.tokens_used).label("tokens"),
                func.sum(BudgetUsage.cost_usd).label("cost"),
            )
            .where(BudgetUsage.tenant_id == tenant_id)
            .where(BudgetUsage.agent_id == agent_id)
            .where(BudgetUsage.period_start == hour_start)
        )

        row = result.one()
        return {
            "tokens_hour": row.tokens or 0,
            "cost_hour": float(row.cost or 0),
        }

    async def _update_redis_counters(
        self,
        tenant_id: int,
        agent_id: str,
        tokens: int,
        cost: Decimal,
    ) -> None:
        """Update Redis counters with TTL."""
        if not self._redis:
            return

        # Calculate TTL until end of hour/day
        now = datetime.now(timezone.utc)
        hour_end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        day_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)

        hour_ttl = int((hour_end - now).total_seconds())
        day_ttl = int((day_end - now).total_seconds())

        # Update counters
        pipe = self._redis.pipeline()

        # Hourly counters
        pipe.incrby(f"budget:{tenant_id}:tokens:hour", tokens)
        pipe.expire(f"budget:{tenant_id}:tokens:hour", hour_ttl)
        pipe.incrbyfloat(f"budget:{tenant_id}:cost:hour", float(cost))
        pipe.expire(f"budget:{tenant_id}:cost:hour", hour_ttl)

        # Daily counters
        pipe.incrby(f"budget:{tenant_id}:tokens:day", tokens)
        pipe.expire(f"budget:{tenant_id}:tokens:day", day_ttl)
        pipe.incrbyfloat(f"budget:{tenant_id}:cost:day", float(cost))
        pipe.expire(f"budget:{tenant_id}:cost:day", day_ttl)

        await pipe.execute()


# Cost per 1K tokens for different models (approximate)
MODEL_COSTS = {
    "gemini-1.5-pro": {"input": Decimal("0.00125"), "output": Decimal("0.00500")},
    "gemini-1.5-flash": {"input": Decimal("0.000075"), "output": Decimal("0.00030")},
    "gpt-4": {"input": Decimal("0.03"), "output": Decimal("0.06")},
    "gpt-4-turbo": {"input": Decimal("0.01"), "output": Decimal("0.03")},
    "gpt-3.5-turbo": {"input": Decimal("0.0005"), "output": Decimal("0.0015")},
}


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> Decimal:
    """
    Calculate cost for a model invocation.

    Args:
        model_name: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Cost in USD
    """
    costs = MODEL_COSTS.get(model_name, MODEL_COSTS["gemini-1.5-pro"])

    input_cost = (Decimal(input_tokens) / 1000) * costs["input"]
    output_cost = (Decimal(output_tokens) / 1000) * costs["output"]

    return input_cost + output_cost
