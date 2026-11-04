"""
Unit tests for IntentHandlers module.

Tests cover:
- Knowledge query handling
- Direct question handling
- Error response creation
- LLM service integration

Usage:
    pytest tests/unit/test_intent_handlers.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.core.agents.ultimate_cva.intent_handlers import IntentHandlers
from src.core.agents.ultimate_cva.models import IntentType, ParsedCommand

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_llm_service():
    """Mock LLM service with async generate_response."""
    service = MagicMock()
    service.default_provider = "mock_provider"
    service.generate_response = AsyncMock(
        return_value={
            "content": "This is a test response",
            "provider": "mock_provider",
        }
    )
    return service


@pytest.fixture
def mock_tool_executor():
    """Mock ToolExecutor."""
    return MagicMock()


@pytest.fixture
def mock_orchestrator():
    """Mock OrchestratorClient."""
    return MagicMock()


@pytest.fixture
def intent_handlers(mock_llm_service, mock_tool_executor, mock_orchestrator):
    """IntentHandlers with mocked services."""
    return IntentHandlers(mock_llm_service, mock_tool_executor, mock_orchestrator)


@pytest.fixture
def knowledge_command():
    """ParsedCommand for knowledge query."""
    return ParsedCommand(
        intent=IntentType.KNOWLEDGE_QUERY,
        original_text="What is machine learning?",
        confidence=0.9,
        parameters={},
    )


@pytest.fixture
def question_command():
    """ParsedCommand for direct question."""
    return ParsedCommand(
        intent=IntentType.DIRECT_QUESTION,
        original_text="How do I optimize performance?",
        confidence=0.85,
        parameters={},
    )


# =============================================================================
# TEST KNOWLEDGE QUERY HANDLER
# =============================================================================


@pytest.mark.asyncio
async def test_knowledge_query_success(intent_handlers, knowledge_command):
    """Test successful knowledge query handling."""
    # Arrange
    context = {"tenant_id": "test"}

    # Act
    result = await intent_handlers.handle_knowledge_query(knowledge_command, context)

    # Assert
    assert result["success"] is True
    assert result["command_type"] == "knowledge_query"
    assert result["source"] == "direct_llm"
    assert "response" in result


@pytest.mark.asyncio
async def test_knowledge_query_calls_llm(intent_handlers, knowledge_command, mock_llm_service):
    """Test that knowledge query calls LLM with correct parameters."""
    # Arrange
    context = {}

    # Act
    await intent_handlers.handle_knowledge_query(knowledge_command, context)

    # Assert
    mock_llm_service.generate_response.assert_called_once()
    call_kwargs = mock_llm_service.generate_response.call_args.kwargs
    assert "prompt" in call_kwargs
    assert "What is machine learning?" in call_kwargs["prompt"]


@pytest.mark.asyncio
async def test_knowledge_query_error_handling(knowledge_command):
    """Test error handling when LLM fails."""
    # Arrange
    failing_service = MagicMock()
    failing_service.default_provider = "failing"
    failing_service.generate_response = AsyncMock(side_effect=Exception("LLM error"))
    handlers = IntentHandlers(failing_service, MagicMock(), MagicMock())

    # Act
    result = await handlers.handle_knowledge_query(knowledge_command, {})

    # Assert
    assert result["success"] is False
    assert "LLM error" in result["error"]


# =============================================================================
# TEST DIRECT QUESTION HANDLER
# =============================================================================


@pytest.mark.asyncio
async def test_direct_question_success(intent_handlers, question_command):
    """Test successful direct question handling."""
    # Arrange
    context = {}

    # Act
    result = await intent_handlers.handle_direct_question(question_command, context)

    # Assert
    assert result["success"] is True
    assert result["command_type"] == "direct_question"
    assert "response" in result


@pytest.mark.asyncio
async def test_direct_question_uses_higher_temperature(
    intent_handlers, question_command, mock_llm_service
):
    """Test that direct questions use higher temperature than knowledge queries."""
    # Act
    await intent_handlers.handle_direct_question(question_command, {})

    # Assert
    call_kwargs = mock_llm_service.generate_response.call_args.kwargs
    assert call_kwargs["temperature"] == 0.7  # Higher than knowledge (0.3)


@pytest.mark.asyncio
async def test_direct_question_error_handling(question_command):
    """Test error handling for direct questions."""
    # Arrange
    failing_service = MagicMock()
    failing_service.default_provider = "failing"
    failing_service.generate_response = AsyncMock(side_effect=Exception("API timeout"))
    handlers = IntentHandlers(failing_service, MagicMock(), MagicMock())

    # Act
    result = await handlers.handle_direct_question(question_command, {})

    # Assert
    assert result["success"] is False
    assert "fallback" in result


# =============================================================================
# TEST PROMPT BUILDING
# =============================================================================


def test_build_knowledge_prompt(intent_handlers):
    """Test knowledge prompt construction."""
    # Act
    prompt = intent_handlers._build_knowledge_prompt("What is AI?")

    # Assert
    assert "What is AI?" in prompt
    assert "factual" in prompt.lower()
    assert "ASCII" in prompt


# =============================================================================
# TEST ERROR RESPONSE
# =============================================================================


def test_error_response_structure(intent_handlers):
    """Test error response contains required fields."""
    # Act
    result = intent_handlers._error_response("test_type", "Test error message")

    # Assert
    assert result["success"] is False
    assert result["error"] == "Test error message"
    assert result["command_type"] == "test_type"
    assert "fallback" in result
    assert "timestamp" in result


# =============================================================================
# TEST CONTENT EXTRACTION
# =============================================================================


def test_extract_content_from_dict(intent_handlers):
    """Test extracting content from dict response."""
    # Arrange
    response = {"content": "Extracted text", "metadata": {}}

    # Act
    result = intent_handlers._extract_content(response)

    # Assert
    assert result == "Extracted text"


def test_extract_content_empty_dict(intent_handlers):
    """Test extracting from dict without content key."""
    # Arrange
    response = {"other_key": "value"}

    # Act
    result = intent_handlers._extract_content(response)

    # Assert
    assert result == ""
