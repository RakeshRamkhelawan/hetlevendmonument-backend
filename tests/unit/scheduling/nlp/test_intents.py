"""Tests for intent classification."""

import pytest

from src.core.scheduling.nlp.intents import ClassifiedIntent, IntentClassifier, IntentType


class TestIntentClassifier:
    """Test suite for IntentClassifier."""

    @pytest.fixture
    def classifier(self):
        """Create an IntentClassifier instance."""
        return IntentClassifier()

    def test_classify_schedule_basic(self, classifier):
        """Test basic schedule intent classification."""
        result = classifier.classify("Schedule a meeting with John tomorrow")

        assert result.intent_type == IntentType.SCHEDULE
        assert result.confidence > 0.5
        assert len(result.matched_keywords) > 0

    def test_classify_schedule_book(self, classifier):
        """Test schedule intent with 'book' keyword."""
        result = classifier.classify("Book a meeting room for the team")

        assert result.intent_type == IntentType.SCHEDULE
        assert result.confidence > 0.5

    def test_classify_reschedule(self, classifier):
        """Test reschedule intent classification."""
        result = classifier.classify("Reschedule my meeting with Jane to next week")

        assert result.intent_type == IntentType.RESCHEDULE
        assert result.confidence > 0.5

    def test_classify_reschedule_move(self, classifier):
        """Test reschedule intent with 'move' keyword."""
        result = classifier.classify("Move the standup to 3pm")

        assert result.intent_type == IntentType.RESCHEDULE

    def test_classify_cancel(self, classifier):
        """Test cancel intent classification."""
        result = classifier.classify("Cancel the meeting on Friday")

        assert result.intent_type == IntentType.CANCEL
        assert result.confidence > 0.5

    def test_classify_query_availability(self, classifier):
        """Test availability query intent."""
        result = classifier.classify("When is John available next week?")

        assert result.intent_type == IntentType.QUERY_AVAILABILITY

    def test_classify_query_conflicts(self, classifier):
        """Test conflict query intent."""
        result = classifier.classify("Do I have any conflicts on Tuesday?")

        assert result.intent_type == IntentType.QUERY_CONFLICTS

    def test_classify_list_events(self, classifier):
        """Test list events intent."""
        result = classifier.classify("Show my meetings for today")

        assert result.intent_type == IntentType.LIST_EVENTS

    def test_classify_update(self, classifier):
        """Test update intent."""
        result = classifier.classify("Change the title to Project Review")

        assert result.intent_type == IntentType.UPDATE

    def test_classify_empty_text(self, classifier):
        """Test classification of empty text."""
        result = classifier.classify("")

        assert result.intent_type == IntentType.UNKNOWN
        assert result.confidence == 0.0

    def test_classify_whitespace_only(self, classifier):
        """Test classification of whitespace-only text."""
        result = classifier.classify("   ")

        assert result.intent_type == IntentType.UNKNOWN

    def test_get_alternative_intents(self, classifier):
        """Test getting alternative intent classifications."""
        alternatives = classifier.get_alternative_intents("Schedule a meeting tomorrow", top_k=3)

        assert len(alternatives) <= 3
        assert all(isinstance(a, ClassifiedIntent) for a in alternatives)
        # First alternative should be SCHEDULE
        assert alternatives[0].intent_type == IntentType.SCHEDULE

    def test_confidence_scoring(self, classifier):
        """Test that confidence scores are reasonable."""
        # Strong schedule intent
        result1 = classifier.classify("Schedule a new meeting with the team")
        assert result1.confidence > 0.7

        # Weaker intent (just 'meeting' without schedule keywords)
        result2 = classifier.classify("I have a meeting")
        # This might be LIST_EVENTS or UNKNOWN depending on patterns
        assert 0.0 <= result2.confidence <= 1.0

    def test_case_insensitivity(self, classifier):
        """Test that classification is case insensitive."""
        result_lower = classifier.classify("schedule a meeting")
        result_upper = classifier.classify("SCHEDULE A MEETING")
        result_mixed = classifier.classify("Schedule A Meeting")

        assert result_lower.intent_type == result_upper.intent_type == result_mixed.intent_type

    def test_punctuation_handling(self, classifier):
        """Test handling of punctuation."""
        result = classifier.classify("Schedule a meeting, please!")

        assert result.intent_type == IntentType.SCHEDULE
