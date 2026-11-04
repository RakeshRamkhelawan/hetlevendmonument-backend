from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agentic.graph.experiment_state import ExperimentState

# Proactive import for the node we're about to create
from src.domains.agentic.nodes.simulator_node import SimulatorNode


@pytest.fixture
def mock_llm_client():
    with patch("src.domains.agentic.nodes.simulator_node.create_llm_client") as mock_create:
        mock_client = AsyncMock()
        mock_create.return_value = mock_client
        # Mock response for generate_response
        mock_client.generate_response.return_value = "Simulated Output"
        yield mock_client


@pytest.mark.asyncio
async def test_simulator_node_execution(mock_llm_client):
    """
    Test that SimulatorNode runs variants against test cases.
    """
    # Arrange
    node = SimulatorNode()
    state: ExperimentState = {
        "prompt_template": "Base Prompt",
        "instruction": "Optimize",
        "variants": ["Variant A", "Variant B"],
        "test_cases": [{"input": "Input 1"}, {"input": "Input 2"}],
        "simulations": {},
        "evaluations": {},
        "best_variant": None,
        "error": None,
    }

    # Act
    new_state = await node.invoke(state)

    # Assert
    assert "simulations" in new_state
    sims = new_state["simulations"]

    # We expect results for 2 variants
    assert len(sims) == 2
    # Check Variant Index 0 (Variant A)
    assert 0 in sims
    # Should have 2 results (one for each test case)
    assert len(sims[0]) == 2
    assert sims[0][0]["output"] == "Simulated Output"

    # Verify LLM call count: 2 variants * 2 test cases = 4 calls
    assert mock_llm_client.generate_response.call_count == 4
