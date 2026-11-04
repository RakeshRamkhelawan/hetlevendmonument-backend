#!/usr/bin/env python3
"""
Unit tests for nlp_endpoints.py
Target: 50% coverage of 164 statements (82 lines covered)

Test Strategy:
- Class 1: TestNLPHealthAndInfo (2 tests) - Health check and intents listing
- Class 2: TestTextParsing (4 tests) - Parse, validate, examples
- Class 3: TestBatchOperations (2 tests) - Batch parsing and statistics
- Class 4: TestErrorHandling (2 tests) - Error scenarios and edge cases

Key Patterns Applied:
1. Mock nlp_parser.parse() for all parse operations
2. Mock IntentType enum for intent-related operations
3. Use valid confidence scores (0.0-1.0)
4. Test both success and failure paths
"""

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

# Mock the dependencies BEFORE importing the endpoint module
sys.modules["src.core.agents.nlp_parser"] = MagicMock()

# Import endpoint functions and models
from src.core.api.nlp_endpoints import (
    BatchParseRequest,
    ParseRequest,
    ValidationRequest,
    batch_parse_texts,
    get_available_intents,
    get_parse_examples,
    get_parser_statistics,
    nlp_system_health,
    parse_text,
    router,
    validate_text,
)


# Mock user for authentication
@pytest.fixture
def mock_user():
    """Mock authenticated user"""
    user = MagicMock()
    user.id = "test_user_001"
    user.username = "testuser"
    user.role = "admin"
    return user


# ============================================================================
# CLASS 1: NLP Health and Info Tests (2 tests)
# ============================================================================


class TestNLPHealthAndInfo:
    """Tests for NLP system health and information endpoints"""

    @pytest.mark.asyncio
    async def test_nlp_system_health_success(self, mock_user):
        """Test NLP system health check"""
        # In TEST_MODE (TESTING=1), require_scopes is bypassed
        # We can call the endpoint directly
        result = await nlp_system_health(mock_user, 1)

        # Assert
        assert result["status"] == "healthy"
        assert result["system"] == "M-MDP Enhanced NLP Parser"
        assert result["version"] == "3.0.0"
        assert result["parser_ready"] is True
        assert "capabilities" in result
        assert len(result["capabilities"]) >= 5

    @pytest.mark.asyncio
    async def test_get_available_intents_success(self, mock_user):
        """Test getting available intents"""
        # Arrange - Mock IntentType enum
        mock_intent_greeting = MagicMock()
        mock_intent_greeting.value = "greeting"

        mock_intent_learning = MagicMock()
        mock_intent_learning.value = "learning_management"

        # Act
        with patch.object(
            sys.modules["src.core.agents.nlp_parser"], "IntentType"
        ) as mock_intent_type:
            mock_intent_type.__iter__ = MagicMock(
                return_value=iter([mock_intent_greeting, mock_intent_learning])
            )

            with patch(
                "src.core.api.nlp_endpoints._get_intent_description",
                return_value="Test description",
            ):
                with patch(
                    "src.core.api.nlp_endpoints._get_intent_examples",
                    return_value=["Example 1"],
                ):
                    with patch("src.core.api.nlp_endpoints._is_mmdp_intent", return_value=True):
                        result = await get_available_intents(mock_user, 1)

        # Assert
        assert result.total_count == 2
        assert len(result.available_intents) == 2
        assert (
            "greeting" in result.mmdp_specific_intents
            or "learning_management" in result.mmdp_specific_intents
        )


# ============================================================================
# CLASS 2: Text Parsing Tests (4 tests)
# ============================================================================


class TestTextParsing:
    """Tests for text parsing and validation endpoints"""

    @pytest.mark.asyncio
    async def test_parse_text_success_high_confidence(self, mock_user):
        """Test successful text parsing with high confidence"""
        # Arrange
        request = ParseRequest(
            text="Start PPO learning", include_confidence=True, include_parameters=True
        )

        mock_parse_result = MagicMock()
        mock_parse_result.confidence = 0.95
        mock_intent = MagicMock()
        mock_intent.value = "learning_management"
        mock_parse_result.intent = mock_intent
        # Use dict for parameters - code now handles this safely
        mock_parse_result.parameters = {"algorithm": "PPO"}

        # Act
        with patch("src.core.api.nlp_endpoints._nlp_parser") as mock_parser:
            mock_parser.parse = MagicMock(return_value=mock_parse_result)

            result = await parse_text(request, mock_user, 1)

        # Assert
        assert result.success is True
        assert result.input_text == "Start PPO learning"
        assert result.intent == "learning_management"
        assert result.confidence == 0.95
        assert result.parameters == {"algorithm": "PPO"}
        assert len(result.suggestions) == 0  # No suggestions for high confidence

    @pytest.mark.asyncio
    async def test_parse_text_low_confidence_with_suggestions(self, mock_user):
        """Test text parsing with low confidence (triggers suggestions)"""
        # Arrange
        request = ParseRequest(
            text="do something", include_confidence=True, include_parameters=False
        )

        mock_parse_result = MagicMock()
        mock_parse_result.confidence = 0.65  # Low confidence
        mock_intent = MagicMock()
        mock_intent.value = "unknown"
        mock_parse_result.intent = mock_intent
        mock_parse_result.parameters = {}

        # Mock IntentType.UNKNOWN
        with patch.object(
            sys.modules["src.core.agents.nlp_parser"], "IntentType"
        ) as mock_intent_type:
            mock_intent_type.UNKNOWN = mock_intent

            # Act
            with patch("src.core.api.nlp_endpoints._nlp_parser") as mock_parser:
                mock_parser.parse = MagicMock(return_value=mock_parse_result)

                result = await parse_text(request, mock_user, 1)

            # Assert
            assert result.success is True
            assert result.confidence == 0.65
            assert (
                len(result.suggestions) >= 2
            )  # Should have suggestions for low confidence + unknown intent
            assert any("rephras" in s.lower() for s in result.suggestions)

    @pytest.mark.asyncio
    async def test_validate_text_success_valid_text(self, mock_user):
        """Test text validation with valid input"""
        # Arrange
        request = ValidationRequest(text="Start learning with PPO algorithm and safety monitoring")

        # Act
        result = await validate_text(request, mock_user, 1)

        # Assert
        assert result.is_valid is True
        assert result.validation_score >= 0.9  # Should be high for valid text with keywords
        assert len(result.issues) == 0

    @pytest.mark.asyncio
    async def test_validate_text_too_short(self, mock_user):
        """Test text validation with too short text"""
        # Arrange
        request = ValidationRequest(text="Hi")

        # Act
        result = await validate_text(request, mock_user, 1)

        # Assert
        # Short text (< 5 chars) gets -0.3 penalty, but 0.7 is still >= 0.5 threshold
        assert result.is_valid is True  # 1.0 - 0.3 = 0.7 (still valid)
        assert result.validation_score == 0.7  # Exact score calculation
        assert any("too short" in issue.lower() for issue in result.issues)
        assert len(result.recommendations) > 0


# ============================================================================
# CLASS 3: Batch Operations Tests (2 tests)
# ============================================================================


class TestBatchOperations:
    """Tests for batch parsing and statistics endpoints"""

    @pytest.mark.asyncio
    async def test_batch_parse_texts_success(self, mock_user):
        """Test batch parsing multiple texts"""
        # Arrange
        request = BatchParseRequest(texts=["Start learning", "Check safety", "Show status"])

        mock_parse_result_1 = MagicMock()
        mock_parse_result_1.confidence = 0.92
        mock_intent_1 = MagicMock()
        mock_intent_1.value = "learning_management"
        mock_parse_result_1.intent = mock_intent_1
        mock_parse_result_1.parameters = {}

        mock_parse_result_2 = MagicMock()
        mock_parse_result_2.confidence = 0.88
        mock_intent_2 = MagicMock()
        mock_intent_2.value = "safety_monitoring"
        mock_parse_result_2.intent = mock_intent_2
        mock_parse_result_2.parameters = {}

        mock_parse_result_3 = MagicMock()
        mock_parse_result_3.confidence = 0.85
        mock_intent_3 = MagicMock()
        mock_intent_3.value = "system_status"
        mock_parse_result_3.intent = mock_intent_3
        mock_parse_result_3.parameters = {}

        # Act
        with patch("src.core.api.nlp_endpoints._nlp_parser") as mock_parser:
            mock_parser.parse = MagicMock(
                side_effect=[
                    mock_parse_result_1,
                    mock_parse_result_2,
                    mock_parse_result_3,
                ]
            )

            result = await batch_parse_texts(request, mock_user, 1)

        # Assert
        assert result["total_texts"] == 3
        assert result["successful_parses"] == 3
        assert result["failed_parses"] == 0
        assert result["average_confidence"] > 0.85
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_get_parser_statistics_success(self, mock_user):
        """Test getting parser statistics"""
        # Act
        result = await get_parser_statistics(mock_user, 1)

        # Assert
        assert "timestamp" in result
        assert "total_parses_today" in result
        assert "average_confidence" in result
        assert "intent_distribution" in result
        assert "performance_metrics" in result
        assert result["total_parses_today"] > 0


# ============================================================================
# CLASS 4: Error Handling Tests (2 tests)
# ============================================================================


class TestErrorHandling:
    """Tests for error scenarios and edge cases"""

    @pytest.mark.asyncio
    async def test_parse_text_parser_failure(self, mock_user):
        """Test parsing failure when parser raises exception"""
        # Arrange
        request = ParseRequest(text="Test text", include_confidence=True, include_parameters=True)

        # Act & Assert
        with patch("src.core.api.nlp_endpoints._nlp_parser") as mock_parser:
            mock_parser.parse = MagicMock(side_effect=Exception("Parser internal error"))

            with pytest.raises(HTTPException) as exc_info:
                await parse_text(request, mock_user, 1)

            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_parse_examples_invalid_intent(self, mock_user):
        """Test getting examples with invalid intent type"""
        # Arrange
        invalid_intent = "invalid_intent_type"

        # Act & Assert
        with patch.object(
            sys.modules["src.core.agents.nlp_parser"], "IntentType"
        ) as mock_intent_type:
            # Mock ValueError when trying to create IntentType from invalid string
            mock_intent_type.side_effect = ValueError("Invalid intent")

            with pytest.raises(HTTPException) as exc_info:
                await get_parse_examples(invalid_intent, mock_user, 1)

            assert exc_info.value.status_code == 400
            assert "Unknown intent type" in str(exc_info.value.detail)


# ============================================================================
# TEST EXECUTION
# ============================================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
