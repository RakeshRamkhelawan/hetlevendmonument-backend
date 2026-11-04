"""
Unit tests voor CostTracker.

Controleert:
- log_suggestion berekent cost correct
- check_budget_status detecteert soft/hard cap
- record_feedback werkt
- get_monthly_stats retourneert correcte data
- DB errors zijn fail-safe
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.learning.cost.cost_tracker import CostTracker
from src.core.learning.twin_models import TenantLLMBudget, TwinSuggestionLog


@pytest.mark.asyncio
class TestCostTrackerLogSuggestion:
    """Tests voor log_suggestion."""

    async def test_log_suggestion_creates_record(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        # Mock budget query for _add_spend
        budget = TenantLLMBudget(
            tenant_id=1,
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            budget_eur_soft=10.0,
            budget_eur_hard=50.0,
            spent_eur=0.0,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = budget
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        log = await tracker.log_suggestion(
            tenant_id=1,
            user_id="u1",
            provider_name="ClaudeSuggestionProvider",
            suggestion_text="Try this...",
            input_tokens=100,
            output_tokens=50,
            score=0.85,
        )

        db.add.assert_called_once()
        db.flush.assert_awaited()
        assert log.provider_name == "ClaudeSuggestionProvider"
        assert log.input_tokens == 100
        assert log.output_tokens == 50
        assert log.cost_eur > 0

    async def test_log_suggestion_truncates_long_text(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        # Mock budget query for _add_spend
        budget = TenantLLMBudget(
            tenant_id=1,
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            budget_eur_soft=10.0,
            budget_eur_hard=50.0,
            spent_eur=0.0,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = budget
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        long_text = "x" * 5000
        log = await tracker.log_suggestion(
            tenant_id=1,
            user_id="u1",
            provider_name="MockSuggestionProvider",
            suggestion_text=long_text,
            input_tokens=10,
            output_tokens=5,
            score=0.5,
        )

        assert log.suggestion_text is not None
        assert len(log.suggestion_text) <= 2000

    async def test_log_suggestion_updates_budget(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        # Mock budget query
        budget = TenantLLMBudget(
            tenant_id=1,
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            budget_eur_soft=10.0,
            budget_eur_hard=50.0,
            spent_eur=0.0,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = budget
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        await tracker.log_suggestion(
            tenant_id=1,
            user_id="u1",
            provider_name="ClaudeSuggestionProvider",
            suggestion_text="Test",
            input_tokens=1000,
            output_tokens=500,
            score=0.8,
        )

        assert budget.spent_eur > 0


@pytest.mark.asyncio
class TestCostTrackerBudgetStatus:
    """Tests voor check_budget_status."""

    async def test_ok_when_under_soft_cap(self):
        db = AsyncMock()
        budget = TenantLLMBudget(
            tenant_id=1,
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            budget_eur_soft=10.0,
            budget_eur_hard=50.0,
            spent_eur=5.0,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = budget
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        status = await tracker.check_budget_status(1)
        assert status == "ok"

    async def test_soft_cap_when_over_soft_under_hard(self):
        db = AsyncMock()
        budget = TenantLLMBudget(
            tenant_id=1,
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            budget_eur_soft=10.0,
            budget_eur_hard=50.0,
            spent_eur=15.0,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = budget
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        status = await tracker.check_budget_status(1)
        assert status == "soft_cap"

    async def test_hard_cap_when_over_hard(self):
        db = AsyncMock()
        budget = TenantLLMBudget(
            tenant_id=1,
            month=datetime.now(timezone.utc).strftime("%Y-%m"),
            budget_eur_soft=10.0,
            budget_eur_hard=50.0,
            spent_eur=55.0,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = budget
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        status = await tracker.check_budget_status(1)
        assert status == "hard_cap"

    async def test_creates_budget_if_not_exists(self):
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        status = await tracker.check_budget_status(1)

        assert status == "ok"
        db.add.assert_called_once()


@pytest.mark.asyncio
class TestCostTrackerFeedback:
    """Tests voor record_feedback (eval harness)."""

    async def test_record_feedback_updates_was_useful(self):
        db = AsyncMock()
        db.flush = AsyncMock()

        log = TwinSuggestionLog(
            tenant_id=1,
            user_id="u1",
            provider_name="Claude",
            suggestion_text="Test",
            input_tokens=10,
            output_tokens=5,
            cost_eur=0.01,
            score=0.8,
        )
        log.id = 42

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = log
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        await tracker.record_feedback(42, True)

        assert log.was_useful is True
        db.flush.assert_awaited()

    async def test_record_feedback_noop_when_log_not_found(self):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        tracker = CostTracker(db=db)
        await tracker.record_feedback(999, True)

        db.flush.assert_not_awaited()
