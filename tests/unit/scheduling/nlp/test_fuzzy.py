"""Tests for fuzzy matching."""

import pytest

from src.core.scheduling.nlp.fuzzy import FuzzyMatcher, ParticipantResolver


class TestFuzzyMatcher:
    """Test suite for FuzzyMatcher."""

    @pytest.fixture
    def matcher(self):
        """Create a FuzzyMatcher instance."""
        return FuzzyMatcher(score_cutoff=70)

    @pytest.fixture
    def sample_candidates(self):
        """Create sample user candidates."""
        return [
            {"id": "1", "name": "John Smith", "email": "john.smith@example.com"},
            {"id": "2", "name": "Jane Doe", "email": "jane.doe@example.com"},
            {"id": "3", "name": "Bob Johnson", "email": "bob.j@example.com"},
            {"id": "4", "name": "Alice Williams", "email": "alice@example.com"},
        ]

    def test_match_exact_name(self, matcher, sample_candidates):
        """Test exact name match."""
        result = matcher.match_participant("John Smith", sample_candidates)

        assert result is not None
        assert result["id"] == "1"

    def test_match_first_name_only(self, matcher, sample_candidates):
        """Test matching by first name only."""
        result = matcher.match_participant("Jane", sample_candidates)

        assert result is not None
        assert result["id"] == "2"

    def test_match_email_prefix(self, matcher, sample_candidates):
        """Test matching by email prefix."""
        result = matcher.match_participant("bob.j", sample_candidates)

        assert result is not None
        assert result["id"] == "3"

    def test_match_typo(self, matcher, sample_candidates):
        """Test matching with typo."""
        result = matcher.match_participant("Jon Smith", sample_candidates)

        assert result is not None
        assert result["id"] == "1"

    def test_no_match_below_threshold(self, matcher, sample_candidates):
        """Test that low similarity doesn't match."""
        result = matcher.match_participant("Completely Different Name", sample_candidates)

        assert result is None

    def test_match_empty_name(self, matcher, sample_candidates):
        """Test matching with empty name."""
        result = matcher.match_participant("", sample_candidates)

        assert result is None

    def test_match_empty_candidates(self, matcher):
        """Test matching with empty candidates list."""
        result = matcher.match_participant("John", [])

        assert result is None

    def test_match_multiple_participants(self, matcher, sample_candidates):
        """Test matching multiple participants."""
        names = ["John", "Jane", "Unknown Person"]
        matched, unmatched = matcher.match_multiple_participants(names, sample_candidates)

        assert len(matched) == 2
        assert len(unmatched) == 1
        assert "Unknown Person" in unmatched

    def test_match_location_exact(self, matcher):
        """Test exact location match."""
        locations = ["Conference Room A", "Meeting Room B", "Zoom"]
        result = matcher.match_location("Conference Room A", locations)

        assert result == "Conference Room A"

    def test_match_location_fuzzy(self, matcher):
        """Test fuzzy location match."""
        locations = ["Conference Room A", "Meeting Room B", "Zoom"]
        result = matcher.match_location("Confernce Room A", locations)

        assert result == "Conference Room A"

    def test_suggest_corrections(self, matcher, sample_candidates):
        """Test correction suggestions."""
        suggestions = matcher.suggest_corrections("Jon Smth", sample_candidates, limit=3)

        assert len(suggestions) > 0
        assert suggestions[0]["name"] == "John Smith"
        assert "score" in suggestions[0]

    def test_calculate_similarity(self, matcher):
        """Test similarity calculation."""
        score = matcher.calculate_similarity("hello", "hello")
        assert score == 1.0

        score = matcher.calculate_similarity("hello", "world")
        assert score < 0.5


class TestParticipantResolver:
    """Test suite for ParticipantResolver."""

    @pytest.fixture
    def resolver(self):
        """Create a ParticipantResolver instance."""
        return ParticipantResolver()

    @pytest.fixture
    def sample_candidates(self):
        """Create sample user candidates."""
        return [
            {"id": "1", "name": "John Smith", "email": "john.smith@example.com"},
            {"id": "2", "name": "Jane Doe", "email": "jane.doe@example.com"},
        ]

    def test_resolve_success(self, resolver, sample_candidates):
        """Test successful resolution."""
        result = resolver.resolve("John Smith", sample_candidates)

        assert result is not None
        assert result["id"] == "1"

    def test_resolve_uses_cache(self, resolver, sample_candidates):
        """Test that caching works."""
        # First resolution
        result1 = resolver.resolve("John", sample_candidates)

        # Second should use cache
        result2 = resolver.resolve("John", sample_candidates)

        assert result1 is result2

    def test_resolve_multiple(self, resolver, sample_candidates):
        """Test resolving multiple names."""
        names = ["John", "Jane"]
        resolved, unresolved = resolver.resolve_multiple(names, sample_candidates)

        assert len(resolved) == 2
        assert len(unresolved) == 0

    def test_resolve_multiple_with_unknown(self, resolver, sample_candidates):
        """Test resolving with unknown names."""
        names = ["John", "Unknown Person"]
        resolved, unresolved = resolver.resolve_multiple(names, sample_candidates)

        assert len(resolved) == 1
        assert len(unresolved) == 1
        assert unresolved[0]["name"] == "Unknown Person"
        assert len(unresolved[0]["suggestions"]) > 0

    def test_clear_cache(self, resolver, sample_candidates):
        """Test cache clearing."""
        resolver.resolve("John", sample_candidates)
        assert len(resolver._cache) > 0

        resolver.clear_cache()
        assert len(resolver._cache) == 0

    def test_preload_cache(self, resolver, sample_candidates):
        """Test cache preloading."""
        names = ["John", "Jane"]
        resolver.preload_cache(names, sample_candidates)

        assert len(resolver._cache) == 2
