"""
Cost Tracker -- per-suggestion cost logging and budget enforcement.

Usage:
    tracker = CostTracker(db)
    await tracker.log_suggestion(
        tenant_id=1, user_id="u1", provider_name="Claude",
        suggestion_text="...", input_tokens=100, output_tokens=50, score=0.85
    )
    status = await tracker.check_budget_status(tenant_id=1)
    # status == "ok" | "soft_cap" | "hard_cap"
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config.config import get_settings
from src.core.learning.metrics import record_twin_llm_cost
from src.core.learning.twin_models import TenantLLMBudget, TwinSuggestionLog


class CostTracker:
    """Track LLM suggestion costs and enforce per-tenant budget caps."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        settings = get_settings()
        # Cost per 1M tokens in EUR (configurable via environment)
        self._cost_per_1m_input: dict[str, Decimal] = {
            "ClaudeSuggestionProvider": Decimal(str(settings.TWIN_COST_CLAUDE_INPUT_EUR_PER_1M)),
            "GeminiSuggestionProvider": Decimal(str(settings.TWIN_COST_GEMINI_INPUT_EUR_PER_1M)),
            "LocalSuggestionProvider": Decimal(str(settings.TWIN_COST_LOCAL_INPUT_EUR_PER_1M)),
            "MockSuggestionProvider": Decimal(str(settings.TWIN_COST_LOCAL_INPUT_EUR_PER_1M)),
        }
        self._cost_per_1m_output: dict[str, Decimal] = {
            "ClaudeSuggestionProvider": Decimal(str(settings.TWIN_COST_CLAUDE_OUTPUT_EUR_PER_1M)),
            "GeminiSuggestionProvider": Decimal(str(settings.TWIN_COST_GEMINI_OUTPUT_EUR_PER_1M)),
            "LocalSuggestionProvider": Decimal(str(settings.TWIN_COST_LOCAL_OUTPUT_EUR_PER_1M)),
            "MockSuggestionProvider": Decimal(str(settings.TWIN_COST_LOCAL_OUTPUT_EUR_PER_1M)),
        }

    async def log_suggestion(
        self,
        tenant_id: int,
        user_id: str,
        provider_name: str,
        suggestion_text: str | None,
        input_tokens: int,
        output_tokens: int,
        score: float,
    ) -> TwinSuggestionLog:
        """Log a suggestion with its cost and update monthly spend."""
        cost = self._compute_cost(provider_name, input_tokens, output_tokens)

        # Truncate very long suggestions for storage
        stored_text = suggestion_text[:2000] if suggestion_text else None

        log = TwinSuggestionLog(
            tenant_id=tenant_id,
            user_id=user_id,
            provider_name=provider_name,
            suggestion_text=stored_text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_eur=float(cost),
            score=score,
            expires_at=datetime.now(timezone.utc) + timedelta(days=2555),
        )
        self._db.add(log)
        await self._db.flush()

        # Update monthly budget
        await self._add_spend(tenant_id, cost)

        logger.debug(
            "twin_suggestion_logged",
            tenant_id=tenant_id,
            user_id=user_id,
            provider=provider_name,
            cost_eur=float(cost),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        return log

    async def check_budget_status(self, tenant_id: int) -> str:
        """Check if tenant has exceeded their monthly budget.

        Returns:
            "ok" -- within budget
            "soft_cap" -- soft cap exceeded, use Ollama only
            "hard_cap" -- hard cap exceeded, use Mock only
        """
        budget = await self._get_or_create_budget(tenant_id)
        spent = Decimal(str(budget.spent_eur))
        soft = Decimal(str(budget.budget_eur_soft))
        hard = Decimal(str(budget.budget_eur_hard))

        if spent >= hard:
            return "hard_cap"
        if spent >= soft:
            return "soft_cap"
        return "ok"

    async def record_feedback(
        self,
        log_id: int,
        was_useful: bool,
    ) -> None:
        """Record user feedback on a suggestion (eval harness)."""
        result = await self._db.execute(
            select(TwinSuggestionLog).where(TwinSuggestionLog.id == log_id)
        )
        log = result.scalar_one_or_none()
        if log:
            log.was_useful = was_useful
            await self._db.flush()
            logger.info(
                "twin_suggestion_feedback",
                log_id=log_id,
                was_useful=was_useful,
            )

    async def get_monthly_stats(self, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get monthly suggestion stats for a tenant."""
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")

        # Total suggestions and cost
        total_result = await self._db.execute(
            select(
                func.count(TwinSuggestionLog.id),
                func.sum(TwinSuggestionLog.cost_eur),
            ).where(
                TwinSuggestionLog.tenant_id == tenant_id,
                func.to_char(TwinSuggestionLog.created_at, "YYYY-MM") == current_month,
            )
        )
        total_count, total_cost = total_result.one_or_none() or (0, 0)

        # Feedback stats
        feedback_result = await self._db.execute(
            select(
                func.count(TwinSuggestionLog.id),
            ).where(
                TwinSuggestionLog.tenant_id == tenant_id,
                func.to_char(TwinSuggestionLog.created_at, "YYYY-MM") == current_month,
                TwinSuggestionLog.was_useful == True,  # noqa: E712
            )
        )
        useful_count = feedback_result.scalar() or 0

        budget = await self._get_or_create_budget(tenant_id)

        return {
            "tenant_id": tenant_id,
            "month": current_month,
            "suggestion_count": total_count or 0,
            "total_cost_eur": float(total_cost or 0),
            "useful_count": useful_count or 0,
            "budget_soft_eur": float(budget.budget_eur_soft),
            "budget_hard_eur": float(budget.budget_eur_hard),
            "spent_eur": float(budget.spent_eur),
        }

    def _compute_cost(
        self,
        provider_name: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """Compute cost in EUR for a suggestion."""
        input_cost = (
            self._cost_per_1m_input.get(provider_name, Decimal("0"))
            * Decimal(input_tokens)
            / Decimal(1_000_000)
        )
        output_cost = (
            self._cost_per_1m_output.get(provider_name, Decimal("0"))
            * Decimal(output_tokens)
            / Decimal(1_000_000)
        )
        return input_cost + output_cost

    async def _get_or_create_budget(self, tenant_id: int) -> TenantLLMBudget:
        """Get or create the monthly budget record for a tenant."""
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
                budget_eur_soft=10.0,
                budget_eur_hard=50.0,
                spent_eur=0.0,
            )
            self._db.add(budget)
            await self._db.flush()

        return budget

    async def _add_spend(self, tenant_id: int, cost: Decimal) -> None:
        """Add cost to the tenant's monthly spend."""
        budget = await self._get_or_create_budget(tenant_id)
        # Ensure budget is not a coroutine (defensive)
        if hasattr(budget, "spent_eur"):
            budget.spent_eur = float(Decimal(str(budget.spent_eur)) + cost)
            await self._db.flush()
        record_twin_llm_cost(tenant_id, float(cost))
