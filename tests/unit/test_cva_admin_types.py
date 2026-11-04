"""TDD tests for cva_admin type fixes (B2.3).

get_cva_agent must return UltimateCVAAgent (not dict).
"""

from unittest.mock import AsyncMock, patch


async def test_get_cva_agent_returns_typed_object():
    """get_cva_agent must return an object with execution_history, capabilities, etc."""
    from src.core.api.cva_admin import get_cva_agent

    mock_agent = AsyncMock()
    mock_agent.execution_history = []
    mock_agent.learning_enabled = True
    mock_agent.context_memory = {}
    mock_agent.performance_cache = {}
    mock_agent.capabilities = AsyncMock()
    mock_agent.last_optimization = AsyncMock()
    mock_agent.cva_mode = AsyncMock()
    mock_agent.cva_mode.value = "standard"

    mock_provider = AsyncMock()
    mock_provider.get_or_create = AsyncMock(return_value=mock_agent)

    result = await get_cva_agent(tenant_id=1, cache_provider=mock_provider)

    assert result is mock_agent
    assert hasattr(result, "execution_history")
    assert hasattr(result, "learning_enabled")
