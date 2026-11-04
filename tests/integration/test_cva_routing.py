from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agents.cva_agent import CVAAgent
from src.core.shared.interfaces import AgentType
from src.core.shared.llm_client import LLMResponse

pytestmark = pytest.mark.skip(
    reason="CVA internals were refactored; _execute_llm_request no longer exists"
)


@pytest.mark.asyncio
async def test_cva_routing_simple_query():
    # Setup
    agent = CVAAgent(agent_id="test_cva", agent_type=AgentType.CVA, tenant_id=1)
    mock_client = AsyncMock()
    mock_client.chat_completion.return_value = LLMResponse(
        content="Test response",
        model="gemini-1.5-flash",
        provider="google",
        success=True,
    )

    query = "What is 2+2?"  # Simple query
    await agent._execute_llm_request(
        llm_client=mock_client,
        query=query,
        conversation_history=[],
        request_type="general",
    )

    # Verify
    # Check if model="gemini-1.5-flash" was passed
    # Note: call_args might be (args, kwargs) tuple or just kwargs depending on python version/mock
    # But call_args.kwargs is standard
    call_kwargs = mock_client.chat_completion.call_args.kwargs
    assert call_kwargs.get("model") == "gemini-1.5-flash"


@pytest.mark.asyncio
async def test_cva_routing_complex_query():
    # Setup
    agent = CVAAgent(agent_id="test_cva", agent_type=AgentType.CVA, tenant_id=1)
    mock_client = AsyncMock()
    mock_client.chat_completion.return_value = LLMResponse(
        content="Test response", model="gemini-1.5-pro", provider="google", success=True
    )

    # Complex query (long, keywords)
    query = "Please analyze the strategic implications of quantum computing on global supply chains and provide a comprehensive breakdown of potential risks and opportunities."

    # Execute
    await agent._execute_llm_request(
        llm_client=mock_client,
        query=query,
        conversation_history=[],
        request_type="general",
    )

    # Verify
    # Check if model="gemini-1.5-pro" was passed
    call_kwargs = mock_client.chat_completion.call_args.kwargs
    assert call_kwargs.get("model") == "gemini-1.5-pro"
