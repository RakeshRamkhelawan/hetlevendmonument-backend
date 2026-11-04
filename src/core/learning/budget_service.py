"""Service layer for tenant LLM budget operations (ADR-026 par. 1.2.2).

Abstracts TenantLLMBudget ORM access so core_api layer (admin_learning_endpoints.py)
does not import agent_runtime model files directly -- ADR-034 boundary.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.shared.learning_audit import log_learning_audit_event
from src.core.learning.metrics import set_twin_llm_budget_hard
from src.core.learning.twin_models import TenantLLMBudget
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)


class LearningBudgetService:
    """Read/write service for per-tenant monthly LLM budget caps."""

    DEFAULT_SOFT = 10.0
    DEFAULT_HARD = 50.0

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_budget(
        self, tenant_id: int
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Return current-month budget for tenant_id.

        Returns default values when no DB record exists.
        Prometheus gauge is updated only when a real record is found.
        """
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        result = await self._db.execute(
            select(TenantLLMBudget).where(
                TenantLLMBudget.tenant_id == tenant_id,
                TenantLLMBudget.month == current_month,
            )
        )
        budget = result.scalar_one_or_none()

        if budget is None:
            return {
                "tenant_id": tenant_id,
                "month": current_month,
                "budget_eur_soft": self.DEFAULT_SOFT,
                "budget_eur_hard": self.DEFAULT_HARD,
                "spent_eur": 0.0,
                "remaining_soft": self.DEFAULT_SOFT,
                "remaining_hard": self.DEFAULT_HARD,
                "created_at": None,
                "updated_at": None,
            }

        set_twin_llm_budget_hard(budget.tenant_id, float(budget.budget_eur_hard))
        return {
            "tenant_id": budget.tenant_id,
            "month": budget.month,
            "budget_eur_soft": float(budget.budget_eur_soft),
            "budget_eur_hard": float(budget.budget_eur_hard),
            "spent_eur": float(budget.spent_eur),
            "remaining_soft": max(0.0, float(budget.budget_eur_soft) - float(budget.spent_eur)),
            "remaining_hard": max(0.0, float(budget.budget_eur_hard) - float(budget.spent_eur)),
            "created_at": budget.created_at.isoformat() if budget.created_at else None,
            "updated_at": budget.updated_at.isoformat() if budget.updated_at else None,
        }

    async def update_budget(
        self,
        tenant_id: int,
        budget_eur_soft: float,
        budget_eur_hard: float,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create or update current-month budget for tenant_id.

        Uses try/except IntegrityError to handle concurrent INSERT race on
        the (tenant_id, month) unique constraint.
        """
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        result = await self._db.execute(
            select(TenantLLMBudget).where(
                TenantLLMBudget.tenant_id == tenant_id,
                TenantLLMBudget.month == current_month,
            )
        )
        budget = result.scalar_one_or_none()

        if budget is None:
            budget = TenantLLMBudget(
                tenant_id=tenant_id,
                month=current_month,
                budget_eur_soft=budget_eur_soft,
                budget_eur_hard=budget_eur_hard,
                spent_eur=0.0,
            )
            self._db.add(budget)
            try:
                await self._db.commit()
            except IntegrityError:
                await self._db.rollback()
                result = await self._db.execute(
                    select(TenantLLMBudget).where(
                        TenantLLMBudget.tenant_id == tenant_id,
                        TenantLLMBudget.month == current_month,
                    )
                )
                budget = result.scalar_one()
                budget.budget_eur_soft = budget_eur_soft
                budget.budget_eur_hard = budget_eur_hard
                await self._db.commit()
        else:
            budget.budget_eur_soft = budget_eur_soft
            budget.budget_eur_hard = budget_eur_hard
            await self._db.commit()

        await self._db.refresh(budget)
        set_twin_llm_budget_hard(budget.tenant_id, float(budget.budget_eur_hard))

        async with best_effort("budget update audit log", db_session=self._db):
            await log_learning_audit_event(
                action="budget.updated",
                resource=f"tenant_llm_budget:{tenant_id}:{current_month}",
                tenant_id=tenant_id,
                details={
                    "budget_eur_soft": budget_eur_soft,
                    "budget_eur_hard": budget_eur_hard,
                },
                session=self._db,
            )
            await self._db.commit()

        return {
            "tenant_id": budget.tenant_id,
            "month": budget.month,
            "budget_eur_soft": float(budget.budget_eur_soft),
            "budget_eur_hard": float(budget.budget_eur_hard),
            "spent_eur": float(budget.spent_eur),
            "remaining_soft": max(0.0, float(budget.budget_eur_soft) - float(budget.spent_eur)),
            "remaining_hard": max(0.0, float(budget.budget_eur_hard) - float(budget.spent_eur)),
            "created_at": budget.created_at.isoformat() if budget.created_at else None,
            "updated_at": budget.updated_at.isoformat() if budget.updated_at else None,
        }
