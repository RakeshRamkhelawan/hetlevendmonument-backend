"""Tests for ML Strategy (Phase 2: ML Cold Start solution).

Covers: MLPhase constants, _deterministic_sample (SHA-256 reproducibility),
_rule_check (cross-tenant and missing-approval detection), and MLStrategy init.
"""

from __future__ import annotations

import pytest

from src.core.governance.ml_strategy import MLPhase, MLStrategy


class TestMLPhaseConstants:
    def test_rules_only_value(self) -> None:
        assert MLPhase.RULES_ONLY == "rules_only"

    def test_rules_plus_stats_value(self) -> None:
        assert MLPhase.RULES_PLUS_STATS == "rules_stats"

    def test_rules_plus_ml_value(self) -> None:
        assert MLPhase.RULES_PLUS_ML == "rules_ml"


class TestMLStrategyDeterministicSample:
    """_deterministic_sample must be reproducible and respect the rate."""

    def test_rate_1_always_returns_true(self) -> None:
        event = {"event_id": "abc-123"}
        assert MLStrategy._deterministic_sample(event, rate=1.0) is True

    def test_rate_0_always_returns_false(self) -> None:
        event = {"event_id": "abc-123"}
        assert MLStrategy._deterministic_sample(event, rate=0.0) is False

    def test_same_event_same_rate_is_deterministic(self) -> None:
        event = {"event_id": "test-event-42"}
        result1 = MLStrategy._deterministic_sample(event, rate=0.5)
        result2 = MLStrategy._deterministic_sample(event, rate=0.5)
        assert result1 == result2

    def test_different_event_ids_can_differ(self) -> None:
        """Two different event IDs should not always produce the same result."""
        results = set()
        for i in range(20):
            event = {"event_id": f"event-{i}"}
            results.add(MLStrategy._deterministic_sample(event, rate=0.5))
        # With 20 different IDs and 50% rate, we expect both True and False
        assert len(results) == 2

    def test_missing_event_id_does_not_raise(self) -> None:
        event = {}  # No event_id
        result = MLStrategy._deterministic_sample(event, rate=0.5)
        assert isinstance(result, bool)

    def test_returns_bool(self) -> None:
        event = {"event_id": "test"}
        assert isinstance(MLStrategy._deterministic_sample(event, rate=0.3), bool)


class TestMLStrategyRuleCheck:
    """_rule_check detects cross-tenant access and missing human approval."""

    def test_cross_tenant_access_detected(self) -> None:
        event = {
            "tenant_id": 1,
            "agent_tenant_id": 2,  # Mismatch
            "risk_level": "low",
            "human_approved": True,
        }
        result = MLStrategy._rule_check(event)
        assert result is not None
        assert result["type"] == "cross_tenant_access"

    def test_cross_tenant_confidence_is_high(self) -> None:
        event = {"tenant_id": 1, "agent_tenant_id": 2}
        result = MLStrategy._rule_check(event)
        assert result["confidence"] >= 0.95

    def test_missing_approval_on_high_risk_detected(self) -> None:
        event = {
            "tenant_id": 1,
            "agent_tenant_id": 1,
            "risk_level": "high",
            "human_approved": False,
        }
        result = MLStrategy._rule_check(event)
        assert result is not None
        assert result["type"] == "missing_approval"

    def test_missing_approval_without_flag_detected(self) -> None:
        event = {
            "tenant_id": 1,
            "agent_tenant_id": 1,
            "risk_level": "high",
            # human_approved absent = falsy
        }
        result = MLStrategy._rule_check(event)
        assert result is not None
        assert result["type"] == "missing_approval"

    def test_clean_event_returns_none(self) -> None:
        event = {
            "tenant_id": 1,
            "agent_tenant_id": 1,
            "risk_level": "low",
            "human_approved": True,
        }
        assert MLStrategy._rule_check(event) is None

    def test_medium_risk_approved_returns_none(self) -> None:
        event = {
            "tenant_id": 5,
            "agent_tenant_id": 5,
            "risk_level": "medium",
            "human_approved": False,
        }
        assert MLStrategy._rule_check(event) is None

    def test_cross_tenant_takes_priority_over_missing_approval(self) -> None:
        """Cross-tenant is caught first even when missing_approval also applies."""
        event = {
            "tenant_id": 1,
            "agent_tenant_id": 9,
            "risk_level": "high",
            "human_approved": False,
        }
        result = MLStrategy._rule_check(event)
        assert result["type"] == "cross_tenant_access"


class TestMLStrategyInit:
    def test_init_accepts_db_session(self) -> None:
        from unittest.mock import MagicMock

        strategy = MLStrategy(db=MagicMock())
        assert strategy is not None


class TestMLStrategyStatisticalCheck:
    """_statistical_check detects high latency, z-scores, and inherits rule checks."""

    @pytest.mark.asyncio
    async def test_inherits_cross_tenant_violation(self) -> None:
        from unittest.mock import MagicMock

        strategy = MLStrategy(db=MagicMock())
        event = {"tenant_id": 1, "agent_tenant_id": 2}
        result = await strategy._statistical_check(tenant_id=1, event=event)
        assert result is not None
        assert result["type"] == "cross_tenant_access"

    @pytest.mark.asyncio
    async def test_detects_latency_anomaly(self) -> None:
        from unittest.mock import MagicMock

        strategy = MLStrategy(db=MagicMock())
        event = {"tenant_id": 1, "agent_tenant_id": 1, "latency_ms": 15000}
        result = await strategy._statistical_check(tenant_id=1, event=event)
        assert result is not None
        assert result["type"] == "statistical_latency_anomaly"

    @pytest.mark.asyncio
    async def test_normal_latency_returns_none(self) -> None:
        from unittest.mock import MagicMock

        strategy = MLStrategy(db=MagicMock())
        event = {"tenant_id": 1, "agent_tenant_id": 1, "latency_ms": 200}
        result = await strategy._statistical_check(tenant_id=1, event=event)
        assert result is None


class TestMLStrategyMLCheck:
    """_ml_check evaluates anomaly scores and inherits rule checks."""

    @pytest.mark.asyncio
    async def test_detects_ml_anomaly(self) -> None:
        from unittest.mock import MagicMock

        strategy = MLStrategy(db=MagicMock())
        event = {"tenant_id": 1, "agent_tenant_id": 1, "anomaly_score": 0.92}
        result = await strategy._ml_check(tenant_id=1, event=event)
        assert result is not None
        assert result["type"] == "ml_anomaly_detected"
        assert result["confidence"] == 0.92

    @pytest.mark.asyncio
    async def test_low_risk_score_returns_none(self) -> None:
        from unittest.mock import MagicMock

        strategy = MLStrategy(db=MagicMock())
        event = {"tenant_id": 1, "agent_tenant_id": 1, "risk_score": 0.15}
        result = await strategy._ml_check(tenant_id=1, event=event)
        assert result is None

