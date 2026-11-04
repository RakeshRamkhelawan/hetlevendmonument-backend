"""Tests for Phase 2: Closed Learning Loop - Adaptation Consumption."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.core.agents.learning_loop import AdaptationRule
from src.core.agents.mixins.learning_mixin import LearningMixin


class TestAdaptationRuleMatchesContext:
    """Tests for AdaptationRule.matches_context() method."""

    def test_matches_context_empty_condition_returns_true(self):
        """Rule with no condition should match any context."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition="",
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "test"}) is True

    def test_matches_context_valid_condition_matches(self):
        """Rule should match when all condition keys match context."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition='{"task_type": "email"}',
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "email"}) is True

    def test_matches_context_valid_condition_no_match(self):
        """Rule should not match when condition keys differ."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition='{"task_type": "email"}',
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "chat"}) is False

    def test_matches_context_partial_match(self):
        """Rule should not match when only some condition keys match."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition='{"task_type": "email", "priority": "high"}',
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "email", "priority": "low"}) is False

    def test_matches_context_ignores_operator_key(self):
        """Rule should ignore 'operator' key in condition."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition='{"task_type": "email", "operator": "AND"}',
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "email"}) is True

    def test_matches_context_invalid_json_returns_false(self):
        """Rule with invalid JSON condition should return False safely."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition="not valid json",
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "test"}) is False

    def test_matches_context_dict_condition(self):
        """Rule should handle dict condition directly (not just JSON string)."""
        rule = AdaptationRule(
            id="1",
            name="test",
            condition={"task_type": "email"},
            action="{}",
            parameters={},
            success_metrics=[],
        )
        assert rule.matches_context({"task_type": "email"}) is True


class TestLearningMixinClosedLoop:
    """Tests for LearningMixin closed loop methods."""

    @pytest.fixture
    def learning_mixin(self):
        """Create a LearningMixin instance with learning enabled."""
        mixin = LearningMixin.__new__(LearningMixin)
        mixin._learning_enabled = True
        mixin._learning_tenant_id = 1
        mixin._learning_flag_names = ("learning_enabled",)
        mixin._adaptation_service_instance = None
        mixin._cross_agent_service_instance = None
        mixin._observation_service_instance = None
        mixin.agent_id = "test_agent"
        mixin.agent_type = MagicMock(value="test_type")
        return mixin

    @pytest.mark.asyncio
    async def test_get_active_adaptations_disabled_returns_empty(self, learning_mixin):
        """When learning is disabled, return empty list."""
        learning_mixin._learning_enabled = False
        result = await learning_mixin.get_active_adaptations()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_active_adaptations_learning_disabled_returns_empty(self, learning_mixin):
        """When learning is disabled, adaptation service should not be used."""
        learning_mixin._learning_enabled = False
        result = await learning_mixin.get_active_adaptations()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_active_adaptations_returns_formatted_rules(self, learning_mixin):
        """Should return formatted adaptations from service."""
        mock_rule = MagicMock()
        mock_rule.id = "rule_1"
        mock_rule.name = "Test Rule"
        mock_rule.action = '{"behavior": "optimize"}'
        mock_rule.success_rate = 0.85
        mock_rule.matches_context = MagicMock(return_value=True)

        mock_service = MagicMock()
        mock_service.get_active_rules.return_value = [mock_rule]
        mock_service.load_from_db = AsyncMock()

        with patch.object(
            type(learning_mixin),
            "adaptation_service",
            new_callable=PropertyMock,
            return_value=mock_service,
        ):
            result = await learning_mixin.get_active_adaptations({"task_type": "email"})

        assert len(result) == 1
        assert result[0]["rule_id"] == "rule_1"
        assert result[0]["name"] == "Test Rule"
        assert result[0]["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_get_active_adaptations_filters_by_context(self, learning_mixin):
        """Should filter rules by context matching."""
        matching_rule = MagicMock()
        matching_rule.matches_context = MagicMock(return_value=True)
        non_matching_rule = MagicMock()
        non_matching_rule.matches_context = MagicMock(return_value=False)

        mock_service = MagicMock()
        mock_service.get_active_rules.return_value = [matching_rule, non_matching_rule]
        mock_service.load_from_db = AsyncMock()

        with patch.object(
            type(learning_mixin),
            "adaptation_service",
            new_callable=PropertyMock,
            return_value=mock_service,
        ):
            result = await learning_mixin.get_active_adaptations({"task_type": "email"})

        assert len(result) == 1

    def test_format_adaptations_for_prompt_empty_returns_empty(self, learning_mixin):
        """Empty adaptations list should return empty string."""
        result = learning_mixin.format_adaptations_for_prompt([])
        assert result == ""

    def test_format_adaptations_for_prompt_formats_correctly(self, learning_mixin):
        """Should format adaptations for LLM prompt."""
        adaptations = [
            {
                "rule_id": "1",
                "name": "Optimize Emails",
                "behavior": "Use batch sending",
                "confidence": 0.85,
            }
        ]
        result = learning_mixin.format_adaptations_for_prompt(adaptations)
        assert "Learned optimizations" in result
        assert "Optimize Emails" in result
        assert "Use batch sending" in result
        assert "85%" in result

    def test_format_adaptations_limits_to_5(self, learning_mixin):
        """Should limit adaptations to 5 to control prompt size."""
        adaptations = [
            {"rule_id": str(i), "name": f"Rule {i}", "behavior": f"Behavior {i}", "confidence": 0.5}
            for i in range(10)
        ]
        result = learning_mixin.format_adaptations_for_prompt(adaptations)
        # Should only include first 5
        assert "Rule 0" in result
        assert "Rule 4" in result
        assert "Rule 5" not in result

    @pytest.mark.asyncio
    async def test_get_learning_context_returns_both_adaptations_and_patterns(self, learning_mixin):
        """Should return both own adaptations and cross-agent patterns."""
        mock_adaptation = {"rule_id": "1", "behavior": "test", "confidence": 0.8}
        mock_pattern = MagicMock()
        mock_pattern.trigger_conditions = {"source_agent_type": "other_agent"}
        mock_pattern.learned_behavior = {"tip": "use caching"}
        mock_pattern.confidence_score = 0.9

        # Mock the adaptation service
        mock_adaptation_service = MagicMock()
        mock_adaptation_service.get_active_rules.return_value = []
        mock_adaptation_service.load_from_db = AsyncMock()

        # Mock cross-agent service
        mock_cross_service = AsyncMock()
        mock_cross_service.get_related_patterns.return_value = [mock_pattern]

        with patch.object(learning_mixin, "_adaptation_service_instance", mock_adaptation_service):
            with patch.object(learning_mixin, "_cross_agent_service_instance", mock_cross_service):
                with patch.object(
                    learning_mixin, "get_active_adaptations", return_value=[mock_adaptation]
                ):
                    result = await learning_mixin.get_learning_context_for_orient(
                        {"task_type": "test"}
                    )

        assert "own_adaptations" in result
        assert "cross_agent_patterns" in result
        assert len(result["own_adaptations"]) == 1

    def test_format_learning_context_formats_both_types(self, learning_mixin):
        """Should format both own adaptations and cross-agent patterns."""
        learning_ctx = {
            "own_adaptations": [{"behavior": "Batch process", "confidence": 0.85}],
            "cross_agent_patterns": [
                {"source_type": "PythonPro", "behavior": "Use caching", "confidence": 0.9}
            ],
        }
        result = learning_mixin.format_learning_context_for_prompt(learning_ctx)
        assert "Learned optimizations" in result
        assert "Batch process" in result
        assert "Insights from related specialist agents" in result
        assert "PythonPro" in result
        assert "Use caching" in result

    def test_format_learning_context_empty_returns_empty(self, learning_mixin):
        """Empty context should return empty string."""
        learning_ctx = {"own_adaptations": [], "cross_agent_patterns": []}
        result = learning_mixin.format_learning_context_for_prompt(learning_ctx)
        assert result == ""

    @pytest.mark.asyncio
    async def test_get_learning_context_handles_errors_gracefully(self, learning_mixin):
        """Errors should be handled gracefully and return empty context."""
        mock_service = MagicMock()
        mock_service.load_from_db = AsyncMock(side_effect=Exception("DB Error"))

        with patch.object(learning_mixin, "_adaptation_service_instance", mock_service):
            result = await learning_mixin.get_learning_context_for_orient({"task_type": "test"})

        assert result["own_adaptations"] == []
        assert result["cross_agent_patterns"] == []
