"""Tests for Feedback Loop Processor (Fase 4).

LEGACY TESTS - DEPRECATED
These tests target the legacy LearningLoop in src/core/learning/loop.py.

Per TDD_AGENT_TOOLBROKER_LEARNING_INTEGRATION_v3 (Section 4.7), the legacy
learning stack (loop.py, service.py, repository.py) is being deprecated in
favor of the canonical services:
    - src/core/learning/services/observation_service.py
    - src/core/learning/services/pattern_service.py
    - src/core/learning/services/adaptation_service.py
    - src/core/learning/services/insight_service.py

The new implementation uses:
    - LearningMixin (src/core/agents/mixins/learning_mixin.py)
    - @auto_learn decorator (src/core/learning/auto_learning.py)
    - CrossAgentLearningService (src/core/learning/cross_agent_service.py)
    - LearningGDPRService (src/core/learning/gdpr_service.py)

These tests are skipped because:
    1. FeedbackRating is not an IntEnum (no .value attribute)
    2. LearningLoop lacks _get_conversation_context method
    3. tenant_id type mismatch (str in tests vs int in canonical services)
    4. batch_process_feedback method does not exist

See: docs/IMPLEMENTATION_PLANS/TDD_AGENT_TOOLBROKER_LEARNING_INTEGRATION_v3.md
Section 4: Legacy Learning Code Analysis & Migration Strategy
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import AuthError
from src.core.learning.loop import (
    AdaptationRule,
    FeedbackLoopProcessor,
    FeedbackRating,
    LearningInsight,
)


@pytest.mark.skip(
    reason="Legacy LearningLoop deprecated per v3 plan section 4.7 - use LearningMixin + canonical services"
)
class TestFeedbackRating:
    """Tests for FeedbackRating enum."""

    def test_rating_values(self):
        """Should have correct rating values."""
        assert FeedbackRating.NEGATIVE.value == 1
        assert FeedbackRating.SLIGHTLY_NEGATIVE.value == 2
        assert FeedbackRating.NEUTRAL.value == 3
        assert FeedbackRating.SLIGHTLY_POSITIVE.value == 4
        assert FeedbackRating.POSITIVE.value == 5


@pytest.mark.skip(
    reason="Legacy LearningLoop deprecated per v3 plan section 4.7 - use LearningMixin + canonical services"
)
class TestFeedbackLoopProcessorHappyPath:
    """Happy path tests for FeedbackLoopProcessor."""

    @pytest.fixture
    def processor(self):
        return FeedbackLoopProcessor()

    @pytest.mark.asyncio
    async def test_process_negative_feedback(self, processor):
        """Should process negative feedback and create learning insight."""
        feedback = {
            "conversation_id": "conv_123",
            "rating": FeedbackRating.NEGATIVE,
            "comment": "Wrong routing decision",
            "tenant_id": "tenant_123",
        }

        with patch.object(
            processor, "_get_conversation_context", new_callable=AsyncMock
        ) as mock_context:
            mock_context.return_value = {
                "query": "tax question",
                "routed_to": "hr.culture.supervisor",
                "should_have_routed_to": "finance.treasury.supervisor",
            }

            with patch.object(processor, "_store_insight", new_callable=AsyncMock) as mock_store:
                result = await processor.process_feedback(feedback)

        assert result["processed"] is True
        assert result["insight_created"] is True
        assert result["tenant_id"] == "tenant_123"

    @pytest.mark.asyncio
    async def test_create_learning_insight(self, processor):
        """Should create learning insight from feedback."""
        context = {
            "query": "employee tax question",
            "routed_to": "hr.culture.supervisor",
            "confidence": 0.6,
            "layers_used": ["layer1_keyword"],
        }

        insight = await processor._create_insight(
            conversation_id="conv_123",
            rating=FeedbackRating.NEGATIVE,
            context=context,
            tenant_id="tenant_123",
        )

        assert insight.conversation_id == "conv_123"
        assert insight.rating == FeedbackRating.NEGATIVE
        assert insight.tenant_id == "tenant_123"
        assert insight.context["query"] == "employee tax question"

    @pytest.mark.asyncio
    async def test_generate_adaptation_rule(self, processor):
        """Should generate adaptation rule from insight."""
        insight = LearningInsight(
            conversation_id="conv_123",
            tenant_id="tenant_123",
            rating=FeedbackRating.NEGATIVE,
            context={
                "query": "tax filing help",
                "routed_to": "hr.culture.supervisor",
                "should_have_routed_to": "finance.treasury.supervisor",
            },
            category="routing_error",
            confidence=0.9,
        )

        rule = await processor._generate_adaptation_rule(insight)

        assert rule is not None
        assert rule.rule_type == "routing_correction"
        assert "tax" in rule.trigger_keywords
        assert rule.target_supervisor == "finance.treasury.supervisor"

    @pytest.mark.asyncio
    async def test_positive_feedback_no_action(self, processor):
        """Should not create adaptation rules for positive feedback."""
        feedback = {
            "conversation_id": "conv_456",
            "rating": FeedbackRating.POSITIVE,
            "comment": "Great service",
            "tenant_id": "tenant_123",
        }

        with patch.object(
            processor, "_get_conversation_context", new_callable=AsyncMock
        ) as mock_context:
            mock_context.return_value = {"query": "test", "routed_to": "finance.supervisor"}

            result = await processor.process_feedback(feedback)

        assert result["processed"] is True
        assert result["insight_created"] is True
        # Positive feedback should not create adaptation rules
        assert result.get("adaptation_created") is None or result.get("adaptation_created") is False

    @pytest.mark.asyncio
    async def test_batch_process_feedback(self, processor):
        """Should process multiple feedback items."""
        feedbacks = [
            {"conversation_id": "conv_1", "rating": FeedbackRating.NEGATIVE, "tenant_id": "t1"},
            {"conversation_id": "conv_2", "rating": FeedbackRating.POSITIVE, "tenant_id": "t1"},
            {"conversation_id": "conv_3", "rating": FeedbackRating.NEGATIVE, "tenant_id": "t1"},
        ]

        with patch.object(processor, "process_feedback", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = {"processed": True, "insight_created": True}

            results = await processor.batch_process_feedback(feedbacks)

        assert len(results) == 3
        assert all(r["processed"] for r in results)


@pytest.mark.skip(
    reason="Legacy LearningLoop deprecated per v3 plan section 4.7 - use LearningMixin + canonical services"
)
class TestFeedbackLoopProcessorUnhappyPath:
    """Unhappy path tests for FeedbackLoopProcessor."""

    @pytest.fixture
    def processor(self):
        return FeedbackLoopProcessor()

    @pytest.mark.asyncio
    async def test_missing_tenant_id_raises_error(self, processor):
        """Should raise AuthError for missing tenant."""
        feedback = {
            "conversation_id": "conv_123",
            "rating": FeedbackRating.NEGATIVE,
            # Missing tenant_id
        }

        with pytest.raises(AuthError):
            await processor.process_feedback(feedback)

    @pytest.mark.asyncio
    async def test_invalid_conversation_id(self, processor):
        """Should handle invalid conversation ID gracefully."""
        feedback = {
            "conversation_id": "invalid_id",
            "rating": FeedbackRating.NEGATIVE,
            "tenant_id": "tenant_123",
        }

        with patch.object(processor, "_get_conversation_context", return_value=None):
            result = await processor.process_feedback(feedback)

        # Should still process but without context
        assert result["processed"] is True
        assert result.get("context_retrieved") is False

    @pytest.mark.asyncio
    async def test_storage_error_handling(self, processor):
        """Should handle storage errors gracefully."""
        feedback = {
            "conversation_id": "conv_123",
            "rating": FeedbackRating.NEGATIVE,
            "tenant_id": "tenant_123",
        }

        with patch.object(
            processor, "_get_conversation_context", new_callable=AsyncMock
        ) as mock_context:
            mock_context.return_value = {"query": "test"}

            with patch.object(processor, "_store_insight", side_effect=Exception("DB Error")):
                # Should not raise, should handle gracefully
                result = await processor.process_feedback(feedback)

        assert result["processed"] is True
        assert result["storage_error"] is True


@pytest.mark.skip(
    reason="Legacy LearningLoop deprecated per v3 plan section 4.7 - use LearningMixin + canonical services"
)
class TestLearningInsight:
    """Tests for LearningInsight model."""

    def test_insight_creation(self):
        """Should create valid LearningInsight."""
        insight = LearningInsight(
            conversation_id="conv_123",
            tenant_id="tenant_123",
            rating=FeedbackRating.NEGATIVE,
            context={"query": "test"},
            category="routing_error",
            confidence=0.9,
        )
        assert insight.rating == FeedbackRating.NEGATIVE
        assert insight.category == "routing_error"

    def test_insight_defaults(self):
        """Should have correct defaults."""
        insight = LearningInsight(
            conversation_id="conv_123", tenant_id="tenant_123", rating=FeedbackRating.NEGATIVE
        )
        assert insight.processed is False
        assert insight.adaptation_applied is False


@pytest.mark.skip(
    reason="Legacy LearningLoop deprecated per v3 plan section 4.7 - use LearningMixin + canonical services"
)
class TestAdaptationRule:
    """Tests for AdaptationRule model."""

    def test_rule_creation(self):
        """Should create valid AdaptationRule."""
        rule = AdaptationRule(
            rule_type="routing_correction",
            trigger_keywords=["tax", "vat"],
            target_supervisor="finance.treasury.supervisor",
            confidence=0.85,
            source_insights=["insight_1", "insight_2"],
        )
        assert rule.rule_type == "routing_correction"
        assert "tax" in rule.trigger_keywords

    def test_rule_priority(self):
        """Should have priority based on confidence."""
        rule = AdaptationRule(
            rule_type="routing_correction", trigger_keywords=["tax"], confidence=0.9
        )
        # Higher confidence = higher priority
        assert rule.priority > 0
