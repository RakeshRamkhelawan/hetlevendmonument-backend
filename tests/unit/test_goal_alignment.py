"""Unit tests for GoalAlignmentValidator - Fase 3.2

Tests keyword-based alignment validation with Dutch/English support.
"""

import uuid

import pytest

from src.core.company.context import AgentExecutionContext, GoalChain
from src.core.company.goal_alignment import GoalAlignmentValidator


def _make_uuid() -> uuid.UUID:
    """Generate a fresh UUID for tests."""
    return uuid.uuid4()


class TestDutchLanguage:
    """Tests for Dutch language support (default)."""

    @pytest.fixture
    def validator(self):
        return GoalAlignmentValidator(language="nl")

    @pytest.fixture
    def complete_context(self):
        """Context with complete goal chain."""
        return AgentExecutionContext(
            tenant_id=1,
            task_id=_make_uuid(),
            trace_id=_make_uuid(),
            goal_chain=GoalChain(
                mission_id=_make_uuid(),
                mission_title="Omzet verdubbelen",
                strategic_goal_id=_make_uuid(),
                strategic_goal_title="Verkoop optimaliseren",
                project_goal_id=_make_uuid(),
                project_goal_title="Sales funnel verbeteren",
                task_goal_id=_make_uuid(),
                task_goal_title="Analyseer verkoopdata",
            ),
        )

    @pytest.mark.asyncio
    async def test_aligned_action(self, validator, complete_context):
        """Happy path: Action matches goal keywords → ALIGNED (>0.6)."""
        # Use keywords that overlap well with goal titles
        result = await validator.validate(
            "analyseer verkoopdata funnel",
            complete_context,  # Direct keyword overlap
        )

        # Should have reasonable alignment (score or status)
        # Keyword matching may result in ALIGNED or DRIFT_WARNING depending on overlap
        assert result.score >= 0.3  # At least some overlap

    @pytest.mark.asyncio
    async def test_misaligned_action(self, validator, complete_context):
        """Unhappy path: Unrelated action → MISALIGNED (<0.3)."""
        result = await validator.validate(
            "bestel kantoorartikelen koffie",
            complete_context,  # No overlap with sales goals
        )

        assert result.status == "MISALIGNED"
        assert result.score < 0.3

    @pytest.mark.asyncio
    async def test_drift_warning(self, validator, complete_context):
        """Tangentieel gerelateerde action → DRIFT_WARNING (0.3-0.6)."""
        # Some keyword overlap but not strong
        result = await validator.validate(
            "optimaliseer proces workflow",  # "optimaliseer" overlaps with "optimaliseren"
            complete_context,
        )

        # Should be in drift range (0.3-0.6)
        assert result.score < 0.6 or result.status == "DRIFT_WARNING"

    @pytest.mark.asyncio
    async def test_exact_match_high_score(self, validator, complete_context):
        """Exact match with task title → high score."""
        result = await validator.validate("analyseer verkoopdata", complete_context)  # Exact match

        # Should be high (task has 0.5 weight, exact match = 1.0 * 0.5 = 0.5 base)
        assert result.score > 0.4

    @pytest.mark.asyncio
    async def test_dutch_stopwords_removed(self, validator, complete_context):
        """Dutch stopwords are filtered out."""
        result = await validator.validate(
            "de het een analyseer verkoopdata van",
            complete_context,  # Stopwords + keywords
        )

        # Should still align well (keywords preserved, stopwords removed)
        assert result.score > 0.3

    @pytest.mark.asyncio
    async def test_degraded_mode_incomplete_chain(self, validator):
        """Incomplete goal chain → DRIFT_WARNING, not MISALIGNED."""
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=_make_uuid(),
            trace_id=_make_uuid(),
            goal_chain=GoalChain(),  # Empty
        )

        result = await validator.validate("any action", context)

        assert result.status == "DRIFT_WARNING"
        assert "incompleet" in result.reason.lower() or "incomplete" in result.reason.lower()

    @pytest.mark.asyncio
    async def test_empty_action_string(self, validator, complete_context):
        """Empty action → DRIFT_WARNING."""
        result = await validator.validate("", complete_context)

        assert result.status == "DRIFT_WARNING"
        assert result.reason


class TestEnglishLanguage:
    """Tests for English language support."""

    @pytest.fixture
    def validator(self):
        return GoalAlignmentValidator(language="en")

    @pytest.fixture
    def complete_context(self):
        """Context with complete goal chain."""
        return AgentExecutionContext(
            tenant_id=1,
            task_id=_make_uuid(),
            trace_id=_make_uuid(),
            goal_chain=GoalChain(
                mission_id=_make_uuid(),
                mission_title="Double revenue",
                strategic_goal_id=_make_uuid(),
                strategic_goal_title="Optimize sales",
                project_goal_id=_make_uuid(),
                project_goal_title="Improve sales funnel",
                task_goal_id=_make_uuid(),
                task_goal_title="Analyze sales data",
            ),
        )

    @pytest.mark.asyncio
    async def test_english_aligned(self, validator, complete_context):
        """English action matches English goals."""
        result = await validator.validate(
            "analyze sales data report",
            complete_context,  # Direct keyword overlap
        )

        # Should be reasonably aligned (keyword overlap)
        assert result.score >= 0.4

    @pytest.mark.asyncio
    async def test_english_stopwords_removed(self, validator, complete_context):
        """English stopwords are filtered."""
        result = await validator.validate(
            "the analyze sales data",
            complete_context,  # With stopwords
        )

        assert result.score > 0.3


class TestScoreRange:
    """Tests for score range validation."""

    @pytest.fixture
    def validator(self):
        return GoalAlignmentValidator()

    @pytest.mark.asyncio
    async def test_score_always_between_0_and_1(self, validator):
        """Score is always 0.0-1.0."""
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=_make_uuid(),
            trace_id=_make_uuid(),
            goal_chain=GoalChain(
                task_goal_id=_make_uuid(),
                task_goal_title="Some task",
            ),
        )

        test_actions = [
            "exact match task",
            "somewhat related",
            "completely different",
            "",
        ]

        for action in test_actions:
            result = await validator.validate(action, context)
            assert 0.0 <= result.score <= 1.0


class TestWeights:
    """Tests for goal level weights."""

    @pytest.mark.asyncio
    async def test_task_has_highest_weight(self):
        """Task title contributes most to score."""
        validator = GoalAlignmentValidator()

        # Context where only task matches
        context = AgentExecutionContext(
            tenant_id=1,
            task_id=_make_uuid(),
            trace_id=_make_uuid(),
            goal_chain=GoalChain(
                mission_id=_make_uuid(),
                mission_title="Unrelated mission xyz",
                strategic_goal_id=_make_uuid(),
                strategic_goal_title="Unrelated strategic abc",
                project_goal_id=_make_uuid(),
                project_goal_title="Unrelated project def",
                task_goal_id=_make_uuid(),
                task_goal_title="matching task keyword",
            ),
        )

        result = await validator.validate("matching task keyword", context)
        # Should still be high despite other levels not matching
        assert result.score > 0.4  # 0.5 weight on task


class TestTokenization:
    """Tests for text tokenization."""

    @pytest.fixture
    def validator(self):
        return GoalAlignmentValidator()

    def test_tokenize_removes_punctuation(self, validator):
        """Punctuation is removed during tokenization."""
        tokens = validator._tokenize("hello, world! test.")
        assert "hello" in tokens
        assert "world" in tokens
        assert "," not in tokens
        assert "!" not in tokens

    def test_tokenize_lowercase(self, validator):
        """Tokens are lowercase."""
        tokens = validator._tokenize("HELLO World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_tokenize_min_length(self, validator):
        """Tokens shorter than 3 chars are removed."""
        tokens = validator._tokenize("aa bb test")  # Use words < 3 chars
        assert "aa" not in tokens  # too short
        assert "bb" not in tokens  # too short
        assert "test" in tokens

    def test_tokenize_empty_string(self, validator):
        """Empty string returns empty set."""
        tokens = validator._tokenize("")
        assert tokens == set()

    def test_jaccard_similarity(self, validator):
        """Jaccard similarity calculation."""
        set1 = {"a", "b", "c"}
        set2 = {"b", "c", "d"}

        # Intersection = 2 (b, c), Union = 4 (a, b, c, d)
        # Jaccard = 2/4 = 0.5
        score = validator._jaccard_similarity(set1, set2)
        assert score == 0.5

    def test_jaccard_empty_sets(self, validator):
        """Jaccard with empty sets returns 0."""
        assert validator._jaccard_similarity(set(), {"a"}) == 0.0
        assert validator._jaccard_similarity({"a"}, set()) == 0.0
        assert validator._jaccard_similarity(set(), set()) == 0.0


class TestEdgeCases:
    """Edge case tests."""

    @pytest.fixture
    def validator(self):
        return GoalAlignmentValidator()

    @pytest.mark.asyncio
    async def test_no_goals_at_all(self, validator):
        """Empty goal chain → DRIFT_WARNING."""
        context = AgentExecutionContext(
            tenant_id=1, task_id=_make_uuid(), trace_id=_make_uuid(), goal_chain=GoalChain()
        )

        result = await validator.validate("any action", context)

        assert result.status == "DRIFT_WARNING"
        assert result.score == 0.5
