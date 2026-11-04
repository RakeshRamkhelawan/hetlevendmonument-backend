"""
Slice 1: Unit tests for ConfidenceScorer (RED → GREEN → REFACTOR)
Tests the multi-signal scoring engine with 5 signals and ambiguous detection

Test cases follow the specification:
- Weight distribution: Tag (0.35) + Semantic (0.25) + History (0.20) + Recency (0.10) + User (0.10)
- Ambiguous detection when top 2 candidates differ by < 0.10
- Cold start handling (no history)
- Fail-safe behavior on service failures
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.agents.capabilities.confidence_scorer import ConfidenceScorer
from src.core.agents.capabilities.schemas import (
    ConfidenceScorerInput,
    ConfidenceScorerOutput,
    ScoredProcedure,
)


class TestConfidenceScorerWeighting:
    """Test score calculation with 5-signal weighting"""

    @pytest.mark.asyncio
    async def test_score_combines_all_signals_correctly(self):
        """
        Given: Five candidate procedures with test scores
        When: ConfidenceScorer.score() is called
        Then: Final score must match weighted combination (Tag=0.35, Semantic=0.25, History=0.20, Recency=0.10, User=0.10)
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()

        candidates = [
            {
                "id": str(uuid4()),
                "name": "Invoice Approval",
                "intent_tags": ["invoice", "approval", "finance"],
                "category": "finance",
            }
        ]

        input_data = ConfidenceScorerInput(
            user_intent="Approve invoice for $200",
            candidate_procedures=candidates,
            tenant_id=tenant_id,
            user_id=user_id,
            context={"department": "finance"},
        )

        # Mock the sub-scoring methods
        with patch.object(scorer, "_tag_score", return_value=0.9):
            with patch.object(scorer, "_semantic_score", return_value=0.8):
                with patch.object(scorer, "_history_score", return_value=0.85):
                    with patch.object(scorer, "_recency_score", return_value=0.7):
                        with patch.object(scorer, "_user_override_score", return_value=0.75):
                            # Act
                            result = await scorer.score(input_data)

                            # Assert
                            assert len(result.scored_procedures) == 1
                            scored = result.scored_procedures[0]

                            # Expected: (0.9*0.35) + (0.8*0.25) + (0.85*0.20) + (0.7*0.10) + (0.75*0.10)
                            # = 0.315 + 0.2 + 0.17 + 0.07 + 0.075 = 0.83
                            expected_score = (
                                (0.9 * 0.35)
                                + (0.8 * 0.25)
                                + (0.85 * 0.20)
                                + (0.7 * 0.10)
                                + (0.75 * 0.10)
                            )
                            assert abs(scored.confidence_score - expected_score) < 0.001

    @pytest.mark.asyncio
    async def test_individual_signal_scores_are_stored(self):
        """
        Given: A procedure to score
        When: ConfidenceScorer.score() is called
        Then: All 5 individual signal scores must be captured in ScoredProcedure
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()

        candidates = [{"id": str(uuid4()), "name": "Test Proc", "intent_tags": []}]
        input_data = ConfidenceScorerInput(
            user_intent="test intent",
            candidate_procedures=candidates,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Mock the sub-scoring methods with distinct values
        with patch.object(scorer, "_tag_score", return_value=0.9):
            with patch.object(scorer, "_semantic_score", return_value=0.8):
                with patch.object(scorer, "_history_score", return_value=0.7):
                    with patch.object(scorer, "_recency_score", return_value=0.6):
                        with patch.object(scorer, "_user_override_score", return_value=0.5):
                            # Act
                            result = await scorer.score(input_data)
                            scored = result.scored_procedures[0]

                            # Assert - each signal score is stored
                            assert scored.tag_score == 0.9
                            assert scored.semantic_score == 0.8
                            assert scored.history_score == 0.7
                            assert scored.recency_score == 0.6
                            assert scored.user_override_score == 0.5


class TestAmbiguousDetection:
    """Test ambiguous match detection"""

    @pytest.mark.asyncio
    async def test_ambiguous_flag_when_top_2_differ_by_less_than_threshold(self):
        """
        Given: Two candidates with scores differing by < 0.10
        When: ConfidenceScorer.score() is called
        Then: ambiguous_matches must contain both, and top_match.is_ambiguous must be True
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()

        candidates = [
            {"id": str(uuid4()), "name": "Proc A", "intent_tags": ["invoice"]},
            {"id": str(uuid4()), "name": "Proc B", "intent_tags": ["invoice"]},
        ]

        input_data = ConfidenceScorerInput(
            user_intent="Approve invoice",
            candidate_procedures=candidates,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Mock scoring to return close scores
        with patch.object(scorer, "_tag_score", side_effect=[0.9, 0.85]):
            with patch.object(scorer, "_semantic_score", side_effect=[0.85, 0.85]):
                with patch.object(scorer, "_history_score", side_effect=[0.80, 0.78]):
                    with patch.object(scorer, "_recency_score", side_effect=[0.70, 0.70]):
                        with patch.object(scorer, "_user_override_score", side_effect=[0.75, 0.72]):
                            # Act
                            result = await scorer.score(input_data)

                            # Assert
                            # Top score ≈ (0.9*0.35 + 0.85*0.25 + 0.80*0.20 + 0.70*0.10 + 0.75*0.10) ≈ 0.844
                            # Second ≈ (0.85*0.35 + 0.85*0.25 + 0.78*0.20 + 0.70*0.10 + 0.72*0.10) ≈ 0.791
                            # Diff ≈ 0.053, which is < 0.10, so ambiguous
                            assert result.top_match is not None
                            assert result.top_match.is_ambiguous is True
                            assert len(result.ambiguous_matches) >= 1

    @pytest.mark.asyncio
    async def test_not_ambiguous_when_gap_exceeds_threshold(self):
        """
        Given: Two candidates with scores differing by >= 0.10
        When: ConfidenceScorer.score() is called
        Then: is_ambiguous must be False
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()

        candidates = [
            {"id": str(uuid4()), "name": "Proc A", "intent_tags": ["invoice"]},
            {"id": str(uuid4()), "name": "Proc B", "intent_tags": ["payment"]},
        ]

        input_data = ConfidenceScorerInput(
            user_intent="Approve invoice",
            candidate_procedures=candidates,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Mock scoring with clear gap
        with patch.object(scorer, "_tag_score", side_effect=[0.95, 0.60]):
            with patch.object(scorer, "_semantic_score", side_effect=[0.90, 0.50]):
                with patch.object(scorer, "_history_score", side_effect=[0.85, 0.40]):
                    with patch.object(scorer, "_recency_score", side_effect=[0.80, 0.30]):
                        with patch.object(scorer, "_user_override_score", side_effect=[0.80, 0.30]):
                            # Act
                            result = await scorer.score(input_data)

                            # Assert
                            assert result.top_match is not None
                            assert result.top_match.is_ambiguous is False


class TestColdStart:
    """Test behavior with no execution history"""

    @pytest.mark.asyncio
    async def test_history_score_cold_start_returns_neutral_on_no_history(self):
        """
        Given: User/procedure with no execution history
        When: _history_score() is called
        Then: Must return 0.5 (neutral) instead of 0.0
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()
        procedure_id = uuid4()

        # Mock repository returning no history
        with patch.object(scorer, "_repository") as mock_repo:
            mock_repo.get_execution_history = AsyncMock(return_value=[])

            # Act
            score = await scorer._history_score(
                user_id=user_id, procedure_id=procedure_id, tenant_id=tenant_id
            )

            # Assert
            assert score == 0.5, "Cold start should return neutral 0.5, not 0.0"


class TestFailSafeHandling:
    """Test graceful degradation on service failures"""

    @pytest.mark.asyncio
    async def test_unhappy_path_embedding_service_failure(self):
        """
        Given: Embedding service fails
        When: ConfidenceScorer.score() is called
        Then: Semantic score should be 0.0 (safe), overall score calculated, no crash
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()

        candidates = [{"id": str(uuid4()), "name": "Test Proc", "intent_tags": []}]
        input_data = ConfidenceScorerInput(
            user_intent="test",
            candidate_procedures=candidates,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Mock embedding failure
        with patch.object(scorer, "_tag_score", return_value=0.8):
            with patch.object(
                scorer,
                "_semantic_score",
                side_effect=Exception("Embedding service down"),
            ):
                with patch.object(scorer, "_history_score", return_value=0.7):
                    with patch.object(scorer, "_recency_score", return_value=0.6):
                        with patch.object(scorer, "_user_override_score", return_value=0.5):
                            # Act & Assert - should not raise
                            try:
                                result = await scorer.score(input_data)
                                # Semantic score becomes 0.0 (safe fallback)
                                # Score = 0.8*0.35 + 0.0*0.25 + 0.7*0.20 + 0.6*0.10 + 0.5*0.10
                                # = 0.28 + 0 + 0.14 + 0.06 + 0.05 = 0.53
                                expected = (
                                    (0.8 * 0.35)
                                    + (0.0 * 0.25)
                                    + (0.7 * 0.20)
                                    + (0.6 * 0.10)
                                    + (0.5 * 0.10)
                                )

                                assert result.scored_procedures[0].semantic_score == 0.0
                                assert (
                                    abs(result.scored_procedures[0].confidence_score - expected)
                                    < 0.001
                                )
                            except Exception as e:
                                pytest.fail(
                                    f"ConfidenceScorer should handle service failure gracefully: {e}"
                                )


class TestScoreRangeValidation:
    """Test that scores stay within valid bounds"""

    @pytest.mark.asyncio
    async def test_all_scores_stay_in_0_to_1_range(self):
        """
        Given: Any valid input
        When: ConfidenceScorer.score() is called
        Then: All confidence scores must be in [0.0, 1.0] range
        """
        # Arrange
        scorer = ConfidenceScorer()
        tenant_id = uuid4()
        user_id = uuid4()

        candidates = [
            {"id": str(uuid4()), "name": "Proc A", "intent_tags": ["test"]},
            {"id": str(uuid4()), "name": "Proc B", "intent_tags": ["test"]},
            {"id": str(uuid4()), "name": "Proc C", "intent_tags": ["test"]},
        ]

        input_data = ConfidenceScorerInput(
            user_intent="some intent",
            candidate_procedures=candidates,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Mock with valid scores
        with patch.object(scorer, "_tag_score", return_value=0.85):
            with patch.object(scorer, "_semantic_score", return_value=0.75):
                with patch.object(scorer, "_history_score", return_value=0.65):
                    with patch.object(scorer, "_recency_score", return_value=0.55):
                        with patch.object(scorer, "_user_override_score", return_value=0.45):
                            # Act
                            result = await scorer.score(input_data)

                            # Assert
                            for scored in result.scored_procedures:
                                assert 0.0 <= scored.confidence_score <= 1.0
                                assert 0.0 <= scored.tag_score <= 1.0
                                assert 0.0 <= scored.semantic_score <= 1.0
                                assert 0.0 <= scored.history_score <= 1.0
                                assert 0.0 <= scored.recency_score <= 1.0
                                assert 0.0 <= scored.user_override_score <= 1.0
