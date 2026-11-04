from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.agents.learning_loop import LearningPattern, LearningSource, LearningType
from src.core.learning.cross_agent_service import CrossAgentLearningService
from src.core.learning.metrics import (
    record_learning_adaptation_applied,
    record_learning_cross_agent_share,
)
from src.core.learning.services.adaptation_service import AdaptationService
from src.core.learning.services.observation_service import ObservationService
from src.core.learning.services.pattern_service import PatternService
from src.core.monitoring.prometheus_metrics import (
    learning_adaptation_applied,
    learning_cross_agent_shares,
    learning_observations_total,
    learning_patterns_active,
)
from src.core.shared.config import reload_settings


def _counter_value(metric, **labels):
    return metric.labels(**labels)._value.get()


@pytest.mark.asyncio
async def test_observation_service_increments_learning_observation_metric() -> None:
    service = ObservationService(tenant_id=77)
    before = _counter_value(
        learning_observations_total, tenant_id="77", learning_type="pattern_recognition"
    )

    await service.record(
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PATTERN_RECOGNITION,
        context={"agent_id": "agent-1", "task_type": "analysis"},
        observation_data={"result": "ok"},
    )

    after = _counter_value(
        learning_observations_total, tenant_id="77", learning_type="pattern_recognition"
    )
    assert after == before + 1


@pytest.mark.asyncio
async def test_pattern_service_sets_active_pattern_gauge() -> None:
    service = PatternService(tenant_id=78)

    await service.register(
        pattern_type=LearningType.PATTERN_RECOGNITION,
        trigger_conditions={"agent_id": "agent-1", "agent_type": "python_pro"},
        learned_behavior={"recommended_action": "keep"},
        confidence_score=0.9,
    )

    assert learning_patterns_active.labels(tenant_id="78")._value.get() == 1


@pytest.mark.asyncio
async def test_adaptation_service_increments_applied_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()
    service = AdaptationService(tenant_id=79)
    service.rules["rule-1"] = SimpleNamespace(
        active=True,
        condition='{"task": "triage"}',
        action='{"route": "specialist"}',
        trigger_count=0,
        success_count=0,
    )
    before = _counter_value(learning_adaptation_applied, tenant_id="79", outcome="success")

    result = await service.apply("rule-1", {"task": "triage"})

    after = _counter_value(learning_adaptation_applied, tenant_id="79", outcome="success")
    assert result["success"] is True
    assert after == before + 1
    monkeypatch.delenv("FEATURE_LEARNING_ENABLED", raising=False)
    reload_settings()


@pytest.mark.asyncio
async def test_cross_agent_share_increments_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    async def _noop_audit(**kwargs):
        return None

    monkeypatch.setattr(
        "src.core.learning.cross_agent_service.log_learning_audit_event", _noop_audit
    )

    class _SynapseStub:
        async def get_partner_rankings(self, agent_id: str, task_type: str | None = None):
            return []

        async def record_collaboration(self, **kwargs):
            return None

    pattern_service = PatternService(tenant_id=80)
    service = CrossAgentLearningService(
        tenant_id=80,
        pattern_service=pattern_service,
        synapse_network=_SynapseStub(),
    )
    pattern = LearningPattern(
        id="pattern-1",
        pattern_type=LearningType.PATTERN_RECOGNITION,
        description="share me",
        trigger_conditions={"agent_type": "python_pro", "task_type": "analysis"},
        learned_behavior={"recommended_action": "reuse"},
        success_rate=0.9,
        confidence_score=0.9,
        observation_count=5,
    )
    before = _counter_value(
        learning_cross_agent_shares,
        tenant_id="80",
        source_agent_type="python_pro",
        target_agent_type="ai_engineer",
    )

    await service.share_pattern(pattern, source_agent_type="python_pro")

    after = _counter_value(
        learning_cross_agent_shares,
        tenant_id="80",
        source_agent_type="python_pro",
        target_agent_type="ai_engineer",
    )
    assert after == before + 1
    monkeypatch.delenv("FEATURE_LEARNING_ENABLED", raising=False)
    reload_settings()


# =============================================================================
# ADR-026 Digital Twin Production Hardening Metrics Tests
# =============================================================================


class TestTwinLLMMetrics:
    """Test ADR-026 LLM provider metrics."""

    def test_record_provider_failure_increments_counter(self):
        """Test that recording a provider failure increments the counter."""
        from src.core.learning.metrics import (
            TWIN_LLM_PROVIDER_FAILURES,
            record_twin_llm_provider_failure,
        )

        before = TWIN_LLM_PROVIDER_FAILURES.labels(provider="Gemini")._value.get()
        record_twin_llm_provider_failure("Gemini")
        after = TWIN_LLM_PROVIDER_FAILURES.labels(provider="Gemini")._value.get()
        assert after == before + 1

    def test_record_circuit_open_increments_counter(self):
        """Test that recording a circuit open increments the counter."""
        from src.core.learning.metrics import (
            TWIN_LLM_PROVIDER_CIRCUIT_OPEN,
            record_twin_llm_provider_circuit_open,
        )

        before = TWIN_LLM_PROVIDER_CIRCUIT_OPEN.labels(provider="Claude")._value.get()
        record_twin_llm_provider_circuit_open("Claude")
        after = TWIN_LLM_PROVIDER_CIRCUIT_OPEN.labels(provider="Claude")._value.get()
        assert after == before + 1

    def test_record_cost_increments_counter(self):
        """Test that recording LLM cost increments the counter by cost amount."""
        from src.core.learning.metrics import (
            TWIN_LLM_COST_EUR,
            record_twin_llm_cost,
        )

        before = TWIN_LLM_COST_EUR.labels(tenant_id="42")._value.get()
        record_twin_llm_cost(42, 1.5)
        after = TWIN_LLM_COST_EUR.labels(tenant_id="42")._value.get()
        assert after == before + 1.5

    def test_record_zero_cost_does_not_increment(self):
        """Test that recording zero cost does not increment the counter."""
        from src.core.learning.metrics import (
            TWIN_LLM_COST_EUR,
            record_twin_llm_cost,
        )

        before = TWIN_LLM_COST_EUR.labels(tenant_id="99")._value.get()
        record_twin_llm_cost(99, 0.0)
        after = TWIN_LLM_COST_EUR.labels(tenant_id="99")._value.get()
        assert after == before


class TestTwinRetentionMetrics:
    """Test ADR-026 retention metrics."""

    def test_record_retention_deleted_increments_counter(self):
        """Test that recording deleted rows increments the counter."""
        from src.core.learning.metrics import (
            TWIN_RETENTION_DELETED_ROWS,
            record_twin_retention_deleted,
        )

        before = TWIN_RETENTION_DELETED_ROWS.labels(table="user_behavior_observations")._value.get()
        record_twin_retention_deleted("user_behavior_observations", 5)
        after = TWIN_RETENTION_DELETED_ROWS.labels(table="user_behavior_observations")._value.get()
        assert after == before + 5

    def test_record_zero_deleted_does_not_increment(self):
        """Test that recording zero deleted rows does not increment."""
        from src.core.learning.metrics import (
            TWIN_RETENTION_DELETED_ROWS,
            record_twin_retention_deleted,
        )

        before = TWIN_RETENTION_DELETED_ROWS.labels(table="twin_suggestion_log")._value.get()
        record_twin_retention_deleted("twin_suggestion_log", 0)
        after = TWIN_RETENTION_DELETED_ROWS.labels(table="twin_suggestion_log")._value.get()
        assert after == before


class TestTwinAggregationMetrics:
    """Test ADR-026 aggregation metrics."""

    def test_record_aggregation_users_processed_increments_counter(self):
        """Test that recording processed users increments the counter."""
        from src.core.learning.metrics import (
            TWIN_AGGREGATION_USERS_PROCESSED,
            record_twin_aggregation_users_processed,
        )

        before = TWIN_AGGREGATION_USERS_PROCESSED.labels(tenant_id="7")._value.get()
        record_twin_aggregation_users_processed(7, 3)
        after = TWIN_AGGREGATION_USERS_PROCESSED.labels(tenant_id="7")._value.get()
        assert after == before + 3


class TestTwinHardDeleteMetrics:
    """Test ADR-026 hard delete metrics."""

    def test_set_hard_delete_pending_sets_gauge(self):
        """Test that setting pending hard delete count updates the gauge."""
        from src.core.learning.metrics import (
            TWIN_HARD_DELETE_PENDING,
            set_twin_hard_delete_pending,
        )

        set_twin_hard_delete_pending(42)
        assert TWIN_HARD_DELETE_PENDING._value.get() == 42

        set_twin_hard_delete_pending(0)
        assert TWIN_HARD_DELETE_PENDING._value.get() == 0
