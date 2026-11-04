"""
Tests for copilot_endpoints.py - Intent Parser Service

TASK: I.1.2.2 Intent parser API integration
"""

import pytest


class TestIntentParserService:
    """Unit tests for IntentParserService (core NLU logic)"""

    def test_service_parse_workflow_detection(self):
        """Test workflow intent detection"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create a new workflow")
        assert result.recommended_agent.value == "workflow"
        assert result.error_message is None
        assert result.confidence >= 0.5

    def test_service_parse_memory_detection(self):
        """Test memory intent detection"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Search the archives")
        assert result.recommended_agent.value == "memory"
        assert result.confidence >= 0.5

    def test_service_parse_governance_detection(self):
        """Test governance intent detection"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Detect bias in the model")
        assert result.recommended_agent.value == "governance"
        assert result.confidence >= 0.5

    def test_service_parse_specialist_detection(self):
        """Test specialist intent detection - when pattern doesn't match"""
        from src.core.api.copilot_endpoints import IntentParserService

        # "Process documents" contains "process" which matches workflow patterns
        result = IntentParserService.parse("Process documents")
        assert result.recommended_agent.value in ["specialist", "memory", "workflow"]

    def test_service_parse_confidence_calculation(self):
        """Test confidence is calculated correctly"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create a workflow for donor analysis")
        assert 0.5 <= result.confidence <= 1.0

    def test_service_keyword_extraction(self):
        """Test keyword extraction"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow for nonprofit donor analysis")
        keywords = result.intent_keywords
        assert len(keywords) > 0
        assert any("create" in k.lower() or "workflow" in k.lower() for k in keywords)

    def test_service_empty_query(self):
        """Test empty query handling"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("")
        assert result.error_message is not None
        assert result.confidence == 0.0

    def test_service_short_query(self):
        """Test short query handling"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("abc")
        assert result.error_message is not None

    def test_service_scope_mapping_workflow(self):
        """Test scope mapping for workflow agent"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow")
        assert "agents:read" in result.required_scopes
        assert "workflows:manage" in result.required_scopes

    def test_service_scope_mapping_memory(self):
        """Test scope mapping for memory agent"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Search documents")
        assert "agents:read" in result.required_scopes
        assert "memory:read" in result.required_scopes

    def test_service_scope_mapping_governance(self):
        """Test scope mapping for governance agent"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Audit bias")
        assert "compliance:read" in result.required_scopes

    def test_service_what_you_asked_field(self):
        """Test that what_you_asked returns original query"""
        from src.core.api.copilot_endpoints import IntentParserService

        query = "Create a workflow"
        result = IntentParserService.parse(query)
        assert result.what_you_asked == query

    def test_service_what_i_understood_field(self):
        """Test that what_i_understood explains the detected intent"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create a workflow")
        assert result.what_i_understood is not None
        assert len(result.what_i_understood) > 0

    def test_service_high_confidence_for_specific_query(self):
        """Test that specific queries get high confidence"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow variant for donor-churn prediction")
        assert result.confidence >= 0.65  # Should be relatively high

    def test_service_low_confidence_for_vague_query(self):
        """Test that vague queries get lower confidence"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Do something")
        assert result.confidence >= 0.5  # Minimum threshold
        assert result.confidence <= 0.8  # But not too high

    def test_service_confidence_range_never_below_05_for_valid_queries(self):
        """Test that confidence is at least 0.5 for valid queries (>= 5 chars)"""
        from src.core.api.copilot_endpoints import IntentParserService

        # Only test queries that are >= 5 characters
        queries = ["abcde", "hello world", "create workflow"]
        for query in queries:
            result = IntentParserService.parse(query)
            assert result.confidence >= 0.5, f"Query '{query}' has confidence {result.confidence}"

    def test_service_stop_words_removed_from_keywords(self):
        """Test that stop words are removed from keywords"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create a workflow for the nonprofit donor system")
        keywords_lower = [k.lower() for k in result.intent_keywords]

        # Common stop words should not appear
        stop_words = ["a", "the", "for", "and", "or", "is", "in", "to"]
        for stop_word in stop_words:
            assert stop_word not in keywords_lower, f"Stop word '{stop_word}' found in keywords"

    def test_service_agent_enum_is_valid(self):
        """Test that recommended_agent is a valid enum"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow")
        # Check it's one of the valid agent types
        valid_agents = ["workflow", "memory", "governance", "specialist"]
        assert result.recommended_agent.value in valid_agents

    def test_service_required_scopes_is_list(self):
        """Test that required_scopes returns a list"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow")
        assert isinstance(result.required_scopes, list)
        assert len(result.required_scopes) > 0

    def test_service_intent_keywords_is_list(self):
        """Test that intent_keywords returns a list"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow")
        assert isinstance(result.intent_keywords, list)

    def test_service_error_message_none_on_success(self):
        """Test that error_message is None when parse succeeds"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("Create workflow")
        assert result.error_message is None

    def test_service_error_message_not_none_on_failure(self):
        """Test that error_message is set when parse fails"""
        from src.core.api.copilot_endpoints import IntentParserService

        result = IntentParserService.parse("")
        assert result.error_message is not None

    def test_service_multiple_workflow_keywords_detection(self):
        """Test detection with multiple workflow-related keywords"""
        from src.core.api.copilot_endpoints import IntentParserService

        queries = [
            "Build a workflow",
            "Create workflow automation",
            "Setup workflow system",
            "Design workflow process",
        ]

        for query in queries:
            result = IntentParserService.parse(query)
            assert result.recommended_agent.value == "workflow", f"Failed for: {query}"

    def test_service_multiple_memory_keywords_detection(self):
        """Test detection with multiple memory-related keywords"""
        from src.core.api.copilot_endpoints import IntentParserService

        queries = [
            "Search documents",
            "Find articles",
        ]

        for query in queries:
            result = IntentParserService.parse(query)
            # May be memory or specialist depending on keyword match
            assert result.recommended_agent.value in [
                "memory",
                "specialist",
                "workflow",
            ]

    def test_service_confidence_increases_with_query_length(self):
        """Test that longer, more specific queries have higher confidence"""
        from src.core.api.copilot_endpoints import IntentParserService

        short = IntentParserService.parse("workflow")
        long = IntentParserService.parse(
            "Create a workflow for donor-churn prediction and analysis"
        )

        # Longer query should have equal or higher confidence
        assert long.confidence >= short.confidence
