"""
Unit tests for Budget Manager

Tests:
- Budget checking (allowed/blocked)
- Usage recording
- Tier-based defaults
- Alert thresholds
- Usage reports
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.budget_manager import (
    BudgetConfig,
    BudgetExceededError,
    BudgetManager,
    SubscriptionTier,
    calculate_cost,
)


class MockSession:
    """Mock AsyncSession for testing."""

    def __init__(self):
        self.add = MagicMock()
        self.commit = AsyncMock()
        self.execute = AsyncMock()


class TestBudgetConfig:
    """Tests for BudgetConfig."""

    def test_default_config(self):
        """Test default budget config."""
        config = BudgetConfig()

        assert config.max_tokens_per_hour == 10000
        assert config.max_tokens_per_day == 100000
        assert config.max_cost_per_hour == Decimal("1.00")
        assert config.alert_threshold == 0.8

    def test_free_tier_config(self):
        """Test free tier defaults."""
        config = BudgetConfig.for_tier(SubscriptionTier.FREE)

        assert config.max_tokens_per_day == 10000
        assert config.max_cost_per_day == Decimal("1.00")

    def test_enterprise_tier_config(self):
        """Test enterprise tier defaults."""
        config = BudgetConfig.for_tier(SubscriptionTier.ENTERPRISE)

        assert config.max_tokens_per_day == 1000000
        assert config.max_cost_per_day == Decimal("100.00")


class TestBudgetManagerCheck:
    """Tests for budget checking."""

    @pytest.fixture
    def mock_session(self):
        return MockSession()

    @pytest.fixture
    def budget_manager(self, mock_session):
        return BudgetManager(mock_session)

    @pytest.mark.asyncio
    async def test_budget_allows_within_limit(self, budget_manager, mock_session):
        """Test budget allows request within limit."""
        # Mock no usage
        budget_manager._get_current_usage = AsyncMock(
            return_value={
                "tokens_hour": 0,
                "cost_hour": 0.0,
            }
        )

        result = await budget_manager.check_budget(
            tenant_id=1,
            agent_id="agent-1",
            estimated_tokens=1000,
        )

        assert result.allowed is True
        assert result.remaining_tokens > 0

    @pytest.mark.asyncio
    async def test_budget_blocks_when_exceeded(self, budget_manager, mock_session):
        """Test budget blocks when limit exceeded."""
        config = BudgetConfig(max_tokens_per_hour=1000)

        # Mock usage at limit
        budget_manager._get_current_usage = AsyncMock(
            return_value={
                "tokens_hour": 900,
                "cost_hour": 0.0,
            }
        )

        result = await budget_manager.check_budget(
            tenant_id=1,
            agent_id="agent-1",
            estimated_tokens=200,  # Would exceed 1000 limit
            config=config,
        )

        assert result.allowed is False
        assert "limit exceeded" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_budget_blocks_per_task_limit(self, budget_manager, mock_session):
        """Test budget blocks when per-task limit exceeded."""
        config = BudgetConfig(max_tokens_per_task=1000)

        budget_manager._get_current_usage = AsyncMock(
            return_value={
                "tokens_hour": 0,
                "cost_hour": 0.0,
            }
        )

        result = await budget_manager.check_budget(
            tenant_id=1,
            agent_id="agent-1",
            estimated_tokens=2000,  # Exceeds per-task limit
            config=config,
        )

        assert result.allowed is False
        assert "Per-task" in result.reason

    @pytest.mark.asyncio
    async def test_budget_alert_at_threshold(self, budget_manager, mock_session):
        """Test alert triggered at threshold."""
        config = BudgetConfig(
            max_tokens_per_hour=1000,
            alert_threshold=0.8,
        )

        # Mock usage at 85% (above 80% threshold)
        budget_manager._get_current_usage = AsyncMock(
            return_value={
                "tokens_hour": 850,
                "cost_hour": 0.0,
            }
        )

        result = await budget_manager.check_budget(
            tenant_id=1,
            agent_id="agent-1",
            estimated_tokens=50,
            config=config,
        )

        assert result.alert_triggered is True


class TestBudgetManagerUsage:
    """Tests for usage recording."""

    @pytest.fixture
    def mock_session(self):
        return MockSession()

    @pytest.fixture
    def budget_manager(self, mock_session):
        return BudgetManager(mock_session)

    @pytest.mark.asyncio
    async def test_record_usage_creates_entry(self, budget_manager, mock_session):
        """Test recording usage creates database entry."""
        await budget_manager.record_usage(
            tenant_id=1,
            agent_id="agent-1",
            tokens_used=1000,
            cost_usd=Decimal("0.01"),
            model_name="gemini-1.5-pro",
        )

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()


class TestCostCalculation:
    """Tests for cost calculation."""

    def test_calculate_cost_gemini_pro(self):
        """Test cost calculation for Gemini Pro."""
        cost = calculate_cost("gemini-1.5-pro", 1000, 500)

        # Input: 1000 tokens * $0.00125/1K = $0.00125
        # Output: 500 tokens * $0.005/1K = $0.0025
        # Total: $0.00375
        assert cost > Decimal("0")
        assert cost < Decimal("0.01")

    def test_calculate_cost_unknown_model(self):
        """Test cost calculation falls back for unknown model."""
        cost = calculate_cost("unknown-model", 1000, 1000)

        # Should use default costs
        assert cost > Decimal("0")


class TestSubscriptionTier:
    """Tests for subscription tiers."""

    def test_tier_values(self):
        """Test tier enum values."""
        assert SubscriptionTier.FREE.value == "free"
        assert SubscriptionTier.STANDARD.value == "standard"
        assert SubscriptionTier.ENTERPRISE.value == "enterprise"
